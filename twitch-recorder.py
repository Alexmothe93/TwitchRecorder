# Based on https://www.junian.net/python-record-twitch/, itself based from https://slicktechies.com/how-to-watchrecord-twitch-streams-using-livestreamer/

import requests
import os
import time
import json
import sys
import subprocess
import datetime
import configargparse

class TwitchRecorder:

	def __init__(self):
		self.clientID = "jzkbprff40iqj646a697cyrvl0zt2m6" #Client ID of Twitch website
		self.version = "0.1" #To increment to each modification
	
	def run(self):
		# make sure the interval to check user availability is not less than 15 seconds
		if(self.refresh < 15):
			print("Check interval should not be lower than 15 seconds, set check interval to 15 seconds.")
			self.refresh = 15
		
		if self.mode == "recorder":
			self.record()
		elif self.mode == "watcher":
			self.watch()
		else:
			print("Mode not recognized, exiting.")

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
					print('Fixing previously recorded files.')
				for f in videoList:
					recordedFilename = os.path.join(self.recordedPath, f)
					print('Fixing ' + recordedFilename + '.')
					try:
						subprocess.call([self.ffmpegPath, '-err_detect', 'ignore_err', '-i', recordedFilename, '-c', 'copy', os.path.join(self.processedPath,f)])
						os.remove(recordedFilename)
					except Exception as e:
						print(e)
			except Exception as e:
				print(e)

		print(self.version, "- Checking for", self.streamer, "every", self.refresh, "seconds. Record with", self.quality, "quality.")
		self.loopcheck()

	def watch(self):
		while True:
			status, info = self.checkStreamer()
			if status == 0:
				print("Streamer is online, checking if recorder is alive...")
				if self.recorderAlive():
					print("Recorder is alive, waiting 10 minutes.")
					time.sleep(600)
				else:
					self.wakeRecorder()
		
	def recorderAlive(self):
		if os.system("ping -c 1 " + self.recorderIPAddress) == 0:
			return True
		else:
			return False
	
	def wakeRecorder(self):
		print("Wake recorder...")
		subprocess.call(["wakeonlan", self.recorderMACAddress])
		while self.recorderAlive() == False:
			print("Waiting for the recorder to wake up...")
		print("The recorder is awake.")
		
	def checkStreamer(self):
		# 0: online, 
		# 1: offline, 
		# 2: not found, 
		# 3: error
		url = 'https://api.twitch.tv/kraken/streams/' + self.streamer
		info = None
		status = 3
		try:
			r = requests.get(url, headers = {"Client-ID" : self.clientID}, timeout = 15)
			r.raise_for_status()
			info = r.json()
			if info['stream'] == None:
				status = 1
			else:
				status = 0
		except requests.exceptions.RequestException as e:
			if e.response:
				if e.response.reason == 'Not Found' or e.response.reason == 'Unprocessable Entity':
					status = 2

		return status, info

	def loopcheck(self):
		while True:
			status, info = self.checkStreamer()
			if status == 2:
				print("Streamer not found.")
				time.sleep(self.refresh)
			elif status == 3:
				print(datetime.datetime.now().strftime("%Hh%Mm%Ss")," ","unexpected error. will try again in 15 seconds.")
				time.sleep(15)
			elif status == 1:
				print(self.version, "-", self.streamer, "currently offline, checking again in", self.refresh, "seconds.")
				time.sleep(self.refresh)
			elif status == 0:
				print(self.streamer, "online. Stream recording in session.")
				filename = datetime.datetime.now().strftime("%Y-%m-%d %Hh%Mm%Ss") + " - " + self.streamer + " - " + (info['stream']).get("channel").get("status") + ".mp4"
				
				# clean filename from unnecessary characters
				filename = "".join(x for x in filename if x.isalnum() or x in [" ", "-", "_", "."])
				
				recordingFilename = os.path.join(self.recordingPath, filename)
				
				# start streamlink process
				subprocess.call(["streamlink", "--twitch-disable-hosting", "--twitch-oauth-token", self.OAuthToken, "twitch.tv/" + self.streamer, self.quality, "-o", recordingFilename])

				print("Recording stream is done.")
				print("Moving file...")
				try:
					os.rename(recordingFilename, os.path.join(self.recordedPath, filename))
				except:
					print("Error when moving file.")
				if self.fixVideos:
					print("Fixing video file.")
					if(os.path.exists(recordedFilename) is True):
						try:
							subprocess.call([self.ffmpegPath, '-err_detect', 'ignore_err', '-i', recordedFilename, '-c', 'copy', os.path.join(self.processedPath, filename)])
							os.remove(recordedFilename)
						except Exception as e:
							print(e)
					else:
						print("Skip fixing. File not found.")
					print("Fixing is done.")
				print("Going back to checking...")
				time.sleep(self.refresh)

def main(argv):
	twitchRecorder = TwitchRecorder()
	
	args = configargparse.ArgParser(default_config_files=['twitch-recorder.conf'], description="Record automatically Twitch streams.\r\n")
	args.add("-c", "--config", dest='config_file', default='twitch-recorder.conf', type=str)
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
	options = args.parse_args()
	
	print(options)
	print("----------")
	print(args.format_help())
	print("----------")
	print(args.format_values())
	print("----------")
	print("Version:", twitchRecorder.version)
	
	while options.streamer == None or options.streamer == "":
		options.streamer = input("Please specify the streamer to watch: ")
	twitchRecorder.streamer = options.streamer

	twitchRecorder.OAuthToken = options.oauth_token
	twitchRecorder.refresh = options.refresh
	twitchRecorder.mode = options.mode
	twitchRecorder.streamer = options.streamer
	twitchRecorder.quality = options.quality
	twitchRecorder.fixVideos = options.fix_videos
	twitchRecorder.ffmpegPath = options.ffmpeg
	twitchRecorder.rootPath = options.path
	twitchRecorder.recorderIPAddress = options.ip_address
	twitchRecorder.recorderMACAddress = options.mac_address

	twitchRecorder.run()

if __name__ == "__main__":
	main(sys.argv[1:])