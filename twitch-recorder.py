# Based on https://www.junian.net/python-record-twitch/, itself based from https://slicktechies.com/how-to-watchrecord-twitch-streams-using-livestreamer/
#
# Changelog
# Version 0.2 : Complete watch()
# Version 0.3 : Change watch() to check recorder before streamer, fix config file argument, less verbosity
# Version 0.4 : Add WindowsInhibitor class to prevent Windows to sleep/hibernate when recording, used refresh argument in watch mode to set time between 2 checks when recorder is alive, fixed some syntax faults
# Version 0.4.1 : Watcher mode: waiting in seconds, not minutes...
# Version 0.5 : Add logging features, verbose mode and update streamer status according to Twitch Kraken API returns
# Version 0.6 : Adapt to Twitch v5 API due to v3 EOL

import requests
import os
import time
import json
import sys
import subprocess
import datetime
import configargparse
import logging

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
		self.clientID = "jzkbprff40iqj646a697cyrvl0zt2m6" #Client ID of Twitch website
		self.APIheaders = {"Client-ID" : self.clientID, "Accept" : "application/vnd.twitchtv.v5+json"}
		self.version = "0.6" #To increment to each modification
		self.osSleep = None
		if os.name == 'nt':
			self.osSleep = WindowsInhibitor()

	def run(self):
		# make sure the interval to check user availability is not less than 15 seconds
		if(self.refresh < 15):
			logging.warning("Check interval should not be lower than 15 seconds, set check interval to 15 seconds.")
			self.refresh = 15
		
		self.streamerID = self.getStreamerID()

		if self.mode == "recorder":
			self.record()
		elif self.mode == "watcher":
			self.watch()
		elif self.mode == "quit":
			logging.info("Exiting.")
		else:
			logging.error("Mode not recognized, exiting.")
			
	def getStreamerID(self):
		url = 'https://api.twitch.tv/kraken/users?login=' + self.streamerName
		info = None
		try:
			r = requests.get(url, headers = self.APIheaders, timeout = 15)
			r.raise_for_status()
			info = r.json()
			if info['_total'] == 0:
				logging.error("No streamer called "+self.streamerName+" found.")
				self.mode = "quit"
			else:
				if info['_total'] > 1:
					logging.warning("ID search for "+self.streamerName+" didn't return an unique result. First result will be used.")
				return info['users'][0]['_id']
		except requests.exceptions.RequestException as e:
			logging.error("An error has occurred when trying to get streamer id.")
			logging.debug(e)

	def record(self):
		# path to recording stream
		self.recordingPath = os.path.join(self.rootPath, "recording")

		# path to recorded stream
		self.recordedPath = os.path.join(self.rootPath, "recorded")

		# path to finished video, errors removed
		self.processedPath = os.path.join(self.rootPath, "processed")

		# create directory for recordedPath and processedPath if not exist
		if(os.path.isdir(self.recordingPath) is False):
			os.makedirs(self.recordingPath)
		if(os.path.isdir(self.recordedPath) is False):
			os.makedirs(self.recordedPath)

		if self.fixVideos:
			if(os.path.isdir(self.processedPath) is False):
				os.makedirs(self.processedPath)
			# fix videos from previous recording session
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

		logging.info("Checking for "+self.streamerName+" every "+str(self.refresh)+" seconds. Record with "+self.quality+" quality.")
		self.loopcheck()

	def watch(self):
		while True:
			if self.recorderAlive():
				logging.info("Recorder is alive, waiting "+str(self.refresh)+" seconds.")
				time.sleep(self.refresh)
			else:
				logging.info("Recorder is sleeping, checking if "+self.streamerName+" is online.")
				status, info = self.checkStreamer()
				if status == 0:
					logging.info(self.streamerName+" is online.")
					self.wakeRecorder()
				elif status == 1:
					logging.info(self.streamerName+" currently offline, checking again in "+str(self.refresh)+" seconds.")
					time.sleep(self.refresh)
				else:
					logging.error("Unexpected error. Will try again in 15 seconds.")
					time.sleep(15)

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

	def checkStreamer(self):
		# 0: Online
		# 1: Offline
		# 2: Error
		url = 'https://api.twitch.tv/kraken/streams/' + self.streamerID
		info = None
		status = 2
		try:
			r = requests.get(url, headers = self.APIheaders, timeout = 15)
			r.raise_for_status()
			info = r.json()
			if info['stream'] == None:
				status = 1
			else:
				status = 0
		except requests.exceptions.RequestException as e:
			logging.error("An error has occurred when trying to get streamer status.")
			logging.debug(e)

		return status, info

	def loopcheck(self):
		while True:
			status, info = self.checkStreamer()
			if status == 2:
				logging.error("Unexpected error. Will try again in 15 seconds.")
				time.sleep(15)
			elif status == 1:
				logging.info(self.streamerName+" currently offline, checking again in "+str(self.refresh)+" seconds.")
				time.sleep(self.refresh)
			elif status == 0:
				logging.info(self.streamerName+" is online. Stream recording in session.")

				if self.osSleep:
					self.osSleep.inhibit()

				filename = datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss")+" - "+self.streamerName+" - "+(info['stream']).get("channel").get("status")+".mp4"

				# clean filename from unnecessary characters
				filename = "".join(x for x in filename if x.isalnum() or x in [" ", "-", "_", "."])

				recordingFilename = os.path.join(self.recordingPath, filename)

				# start streamlink process
				subprocess.call(["streamlink", "--twitch-disable-hosting", "--twitch-oauth-token", self.OAuthToken, "twitch.tv/" + self.streamerName, self.quality, "-o", recordingFilename])

				logging.info("Recording stream is done.")
				logging.info("Moving file...")
				try:
					os.rename(recordingFilename, os.path.join(self.recordedPath, filename))
				except:
					logging.error("Error when moving file.")
				if self.fixVideos:
					logging.info("Fixing video file.")
					if(os.path.exists(recordedFilename) is True):
						try:
							subprocess.call([self.ffmpegPath, '-err_detect', 'ignore_err', '-i', recordedFilename, '-c', 'copy', os.path.join(self.processedPath, filename)])
							os.remove(recordedFilename)
						except Exception as e:
							logging.error(e)
					else:
						logging.info("Skip fixing. File not found.")
					logging.info("Fixing is done.")

				if self.osSleep:
					self.osSleep.uninhibit()

				logging.info("Going back to checking...")
				time.sleep(self.refresh)

def main(argv):
	twitchRecorder = TwitchRecorder()

	args = configargparse.ArgParser(default_config_files=['twitch-recorder.conf'], description="Record automatically Twitch streams.\r\n")
	args.add("-c", "--config", dest='config_file', is_config_file=True, default='twitch-recorder.conf', type=str)
	args.add("-o", "--oauth-token", help="OAuth Token from your Twitch account.")
	args.add("-s", "--streamer", default=None, help="Indicate the streamer to watch.")
	args.add("-r", "--refresh", help="Time between 2 checks.", type=int)
	args.add("-p", "--path", help="Path to save the records.")
	args.add("-fix", "--fix-videos", action='store_true', default=False, help="Fix videos with ffmpeg.")
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
	twitchRecorder.streamerName = options.streamer

	twitchRecorder.OAuthToken = options.oauth_token
	twitchRecorder.refresh = options.refresh
	twitchRecorder.mode = options.mode
	twitchRecorder.quality = options.quality
	twitchRecorder.fixVideos = options.fix_videos
	twitchRecorder.ffmpegPath = options.ffmpeg
	twitchRecorder.rootPath = options.path
	twitchRecorder.recorderIPAddress = options.ip_address
	twitchRecorder.recorderMACAddress = options.mac_address

	twitchRecorder.run()

if __name__ == "__main__":
	main(sys.argv[1:])
