# Based on https://www.junian.net/python-record-twitch/, itself based from https://slicktechies.com/how-to-watchrecord-twitch-streams-using-livestreamer/
#
# Changelog
# Version 0.2 : Complete watch()
# Version 0.3 : Change watch() to check recorder before streamer, fix config file argument, less verbosity
# Version 0.4 : Add WindowsInhibitor class to prevent Windows to sleep/hibernate when recording, used refresh argument in watch mode to set time between 2 checks when recorder is alive, fixed some syntax faults
# Version 0.4.1 : Watcher mode: waiting in seconds, not minutes...
# Version 0.5 : Add logging features, verbose mode and update streamer status according to Twitch Kraken API returns
# Version 0.6 : Adapt to Twitch v5 API due to v3 EOL
# Version 0.7 : Add streamlink option to disable Twitch ads
# Version 0.8 : Fix streamlink not exiting after some streams ending
# Version 0.9 : The script retries every 10 minutes when the streamer isn't found (potentially banned), and retry immediatly when a stream ends
# Version 0.10 : Adaptation to Twitch Helix API, errors are more explicit in non verbose mode, fix an issue on videos fix feature
# Version 0.11 : Fix crashes when the network connection fail
# Version 0.12 : Added streamlink path argument to fix a potential issue of selecting the wrong path

import requests
import os
import time
import json
import sys
import subprocess
import datetime
import configargparse
import logging
from multiprocessing import Process

class WindowsInhibitor:
	'''Prevent OS sleep/hibernate in windows; code from:
	https://github.com/h3llrais3r/Deluge-PreventSuspendPlus/blob/master/preventsuspendplus/core.py
	API documentation:
	https://msdn.microsoft.com/en-us/library/windows/desktop/aa373208(v=vs.85).aspx'''
	ES_CONTINUOUS = 0x80000000
	ES_SYSTEM_REQUIRED = 0x00000001

	def __init__(self):
		pass

	def inhibit(self):
		import ctypes
		logging.info("Preventing Windows from going to sleep.")
		ctypes.windll.kernel32.SetThreadExecutionState(
			WindowsInhibitor.ES_CONTINUOUS | \
			WindowsInhibitor.ES_SYSTEM_REQUIRED)

	def uninhibit(self):
		import ctypes
		logging.info("Allowing Windows to go to sleep.")
		ctypes.windll.kernel32.SetThreadExecutionState(
			WindowsInhibitor.ES_CONTINUOUS)

class TwitchRecorder:

	def __init__(self):
		self.version = "0.12" #To increment to each modification

		self.clientID = ""
		self.clientSecret = ""
		self.OAuthToken = ""
		self.refresh = 30
		self.mode = "recorder"
		self.quality = "best"
		self.fixVideos = False
		self.streamlinkPath = "C:\Program Files\Streamlink\bin\streamlink.exe"
		self.ffmpegPath = "C:\ffmpeg\bin\ffmpeg.exe"
		self.rootPath = "C:\TwitchRecorder"
		self.recorderIPAddress = ""
		self.recorderMACAddress = ""
		self.osSleep = None
		self.procs = []
		if os.name == 'nt':
			self.osSleep = WindowsInhibitor()

	def run(self):
		self.APIheaders = {"Client-ID" : self.clientID, "Authorization" : "Bearer "+self.OAuthToken}

		# Make sure the interval to check user availability is not too low
		if(self.refresh < 1):
			logging.warning("Check interval should not be lower than 1 second, set check interval to 15 seconds.")
			self.refresh = 15
		
		if self.mode == "recorder":
			self.record()
		elif self.mode == "watcher":
			self.watch()
		else:
			logging.error("Mode not recognized, exiting.")

	def updateOAuthToken(self):
		url = 'https://id.twitch.tv/oauth2/token'
		try:
			r = requests.post(url, data = {"client_id" : self.clientID, "client_secret" : self.clientSecret, "grant_type" : "client_credentials"})
			r.raise_for_status()
			self.OAuthToken = r.json()["access_token"]
			self.APIheaders = {"Client-ID" : self.clientID, "Authorization" : "Bearer "+self.OAuthToken}
		except requests.exceptions.RequestException as e:
			logging.error("Unable to authenticate, check client ID and client secret, error returned: "+str(e))

	def getStreamerID(self, streamerName):
		url = 'https://api.twitch.tv/helix/users?login=' + streamerName
		info = None
		while info == None or info['_total'] == 0:
			try:
				r = requests.get(url, headers = self.APIheaders, timeout = 15)
				r.raise_for_status()
				info = r.json()
				logging.debug(info)
				if len(info['data']) == 0:
					logging.error("No streamer called "+streamerName+" found. Retry in 10 minutes.")
					time.sleep(600)
				else:
					if len(info['data']) > 1:
						logging.warning("ID search for "+streamerName+" didn't return an unique result. First result will be used.")
					return info['data'][0]['id']
			except requests.exceptions.HTTPError as e:
				if r.status_code == 401:
					logging.info("Authentication required.")
					self.updateOAuthToken()
				else:
					logging.error("An HTTP error occurred while trying to get the streamer id: "+str(e))
					time.sleep(1)
			except requests.exceptions.RequestException as e:
				logging.error("An error occurred while trying to get the streamer id: "+str(e))
				time.sleep(1)

	def record(self):
		# Path to recording stream
		self.recordingPath = os.path.join(self.rootPath, "recording")

		# Path to recorded stream
		self.recordedPath = os.path.join(self.rootPath, "recorded")

		# Path to finished video, errors removed
		self.processedPath = os.path.join(self.rootPath, "processed")

		# Create directories for recordingPath, recordedPath and processedPath if not exist
		if(os.path.isdir(self.recordingPath) is False):
			os.makedirs(self.recordingPath)
		if(os.path.isdir(self.recordedPath) is False):
			os.makedirs(self.recordedPath)
		if self.fixVideos:
			if(os.path.isdir(self.processedPath) is False):
				os.makedirs(self.processedPath)
			
			# Fix videos from previous recording session
			try:
				videoList = [f for f in os.listdir(self.recordedPath) if os.path.isfile(os.path.join(self.recordedPath, f))]
				if(len(videoList) > 0):
					logging.info("Fixing previously recorded files.")
				for f in videoList:
					recordedFilename = os.path.join(self.recordedPath, f)
					logging.info("Fixing "+recordedFilename+".")
					try:
						subprocess.call([self.ffmpegPath, '-err_detect', 'ignore_err', '-i', recordedFilename, '-c', 'copy', os.path.join(self.processedPath,f)])
						os.remove(recordedFilename)
					except Exception as e:
						logging.error(e)
			except Exception as e:
				logging.error(e)

		for streamer in self.streamers:
			proc = Process(target=self.loopcheckStreamer, args=(streamer,))
			self.procs.append(proc)
			proc.start()

		for proc in self.procs:
			proc.join()

	def watch(self):
		streamersIDs = []
		for streamer in self.streamers:
			streamersIDs.append(self.getStreamerID(streamer))
		while True:
			if self.recorderAlive():
				logging.info("Recorder is alive.")
			else:
				logging.info("Recorder is sleeping.")
				for streamerID in streamersIDs:
					logging.info("Checking if "+streamerID+" is online...")
					status, info = self.checkStreamer(streamerID)
					if status == 0:
						logging.info(streamerID+" is online.")
						self.wakeRecorder()
						break
					elif status == 1:
						logging.info(streamerID+" is currently offline.")
					else:
						logging.error("Unexpected error.")
			logging.info("Checking again in "+str(self.refresh)+" seconds.")
			time.sleep(self.refresh)

	def recorderAlive(self):
		if os.system("ping -c 1 " + self.recorderIPAddress + " > /dev/null") == 0:
			return True
		else:
			return False

	def wakeRecorder(self):
		logging.info("Wake recorder...")
		subprocess.call(["wakeonlan", self.recorderMACAddress])
		while self.recorderAlive() == False:
			logging.info("Waiting for the recorder to wake up...")
		logging.info("The recorder is awake.")

	def checkStreamer(self, streamerID):
		# 0: Online
		# 1: Offline
		# 2: Error
		url = 'https://api.twitch.tv/helix/streams?user_id='+streamerID
		info = None
		status = 2
		try:
			r = requests.get(url, headers = self.APIheaders, timeout = 15)
			r.raise_for_status()
			info = r.json()
			if len(info['data']) == 0:
				status = 1
			elif len(info['data']) == 1:
				status = 0
		except requests.exceptions.HTTPError as e:
			if r.status_code == 401:
				logging.info("Authentication required.")
				self.updateOAuthToken()
			else:
				logging.error("An HTTP error occurred while trying to get the streamer status: "+str(e))
		except requests.exceptions.RequestException as e:
			logging.error("An error occurred while trying to get the streamer status: "+str(e))

		return status, info

	def loopcheckStreamer(self, streamerName):
		streamerID = self.getStreamerID(streamerName)
		logging.info("Checking for "+streamerName+" every "+str(self.refresh)+" seconds. Record with "+self.quality+" quality.")
		while True:
			status, info = self.checkStreamer(streamerID)
			if status == 2:
				logging.error("Unexpected error. Will try again in 15 seconds.")
				time.sleep(15)
			elif status == 1:
				logging.info(streamerName+" currently offline, checking again in "+str(self.refresh)+" seconds.")
				time.sleep(self.refresh)
			elif status == 0:
				logging.info(streamerName+" is online. Stream recording in session.")

				if self.osSleep:
					self.osSleep.inhibit()

				filename = datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+" - "+self.streamerName+" - "+(info['data'][0]["title"])+".mp4"

				# Clean filename from unnecessary characters
				filename = "".join(x for x in filename if x.isalnum() or x in [" ", "-", "_", "."])

				recordingFilename = os.path.join(self.recordingPath, filename)

				# Start streamlink process
				subprocess.call([self.streamlinkPath, "--twitch-disable-hosting", "--twitch-disable-ads", "twitch.tv/" + self.streamerName, self.quality, "-o", recordingFilename])

				logging.info("Recording stream is done.")
				logging.info("Moving file...")
				try:
					os.rename(recordingFilename, os.path.join(self.recordedPath, filename))
				except:
					logging.error("Error when moving file.")
				if self.fixVideos:
					logging.info("Fixing video file.")
					if(os.path.exists(os.path.join(self.recordedPath, filename)) is True):
						try:
							subprocess.call([self.ffmpegPath, '-err_detect', 'ignore_err', '-i', os.path.join(self.recordedPath, filename), '-c', 'copy', os.path.join(self.processedPath, filename)])
							os.remove(os.path.join(self.recordedPath, filename))
						except Exception as e:
							logging.error(e)
					else:
						logging.info("Skip fixing. File not found.")
					logging.info("Fixing is done.")

				if self.osSleep:
					self.osSleep.uninhibit()

				logging.info("Going back to checking...")

def main(argv):
	twitchRecorder = TwitchRecorder()

	args = configargparse.ArgParser(default_config_files=['twitch-recorder.conf'], description="Records automatically lives from a Twitch streamer.\r\n")
	args.add("-conf", "--config", dest='config_file', is_config_file=True, default='twitch-recorder.conf', type=str)
	args.add("-cid", "--client-id", help="Client ID of the registered Twitch app.")
	args.add("-sec", "--client-secret", help="Client secret of the registered Twitch app.")
	args.add("-o", "--oauth-token", help="OAuth Token to use with registered Twitch app.")
	args.add("-s", "--streamer", default=None, help="Indicate the streamer to watch.", action="append")
	args.add("-r", "--refresh", help="Time between 2 checks.", type=int)
	args.add("-p", "--path", help="Path to save the records.")
	args.add("-fix", "--fix-videos", action='store_true', default=False, help="Fix videos with ffmpeg.")
	args.add("-sl", "--streamlink", help="Path to the streamlink binary.")
	args.add("-f", "--ffmpeg", help="Path to the ffmpeg binary.")
	args.add("-i", "--ip-address", help="Recorder IP address.")
	args.add("-ma", "--mac-address", help="Recorder MAC address.")
	args.add("-m", "--mode", choices=["recorder", "watcher"], default="recorder", help="Mode to launch the script.")
	args.add("-q", "--quality", help="Specify the quality to record (examples: best, worst, audio_only, 720p60, 1080p).")
	args.add("-v", "--verbose", help="Debug mode.", action='store_true')
	options = args.parse_args()
	if options.verbose:
		logging.basicConfig(level=logging.DEBUG, format='[%(levelname)s] v'+twitchRecorder.version+' %(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
		logging.debug(options)
		logging.debug(args.format_values())
	else:
		logging.basicConfig(level=logging.INFO, format='v'+twitchRecorder.version+' %(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

	while options.streamer == None or options.streamer == "":
		options.streamer = input("Please specify the streamer to watch: ")
	twitchRecorder.streamers = options.streamer

	twitchRecorder.clientID = options.client_id
	twitchRecorder.clientSecret = options.client_secret
	twitchRecorder.OAuthToken = options.oauth_token
	twitchRecorder.refresh = options.refresh
	twitchRecorder.mode = options.mode
	twitchRecorder.quality = options.quality
	twitchRecorder.fixVideos = options.fix_videos
	twitchRecorder.streamlinkPath = options.streamlink
	twitchRecorder.ffmpegPath = options.ffmpeg
	twitchRecorder.rootPath = options.path
	twitchRecorder.recorderIPAddress = options.ip_address
	twitchRecorder.recorderMACAddress = options.mac_address

	twitchRecorder.run()

if __name__ == "__main__":
	main(sys.argv[1:])
