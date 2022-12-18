# TwitchRecorder
TwitchRecorder records automatically lives from a Twitch streamer.

# Requirements
- Python 3 with requests and configargparse modules
- Streamlink to record streams
- [Optional] FFmpeg to fix video files
- [Optional] For watcher mode (Linux) : wakeonlan 
- Register an app here : https://dev.twitch.tv/console/apps/create to obtain a Client ID and OAuth token

# How to use it
1. Install [python (and pip)](https://www.python.org/downloads/) and [streamlink](https://github.com/streamlink/windows-builds/releases) on your computer.
2. [Download the source code](https://github.com/Alexmothe93/TwitchRecorder/archive/refs/heads/master.zip) and extract it where you want.
3. Install python dependencies with `pip install -r /path/to/requirements.txt`.
4. Rename `twitch-recorder.conf.example` into `twitch-recorder.conf`.
5. Register a Twitch API access here : https://dev.twitch.tv/console/apps/create.
6. Put client ID et and secret obtained in the `twitch-recorder.conf` file.
7. Launch `twitch-recorder.py` file, enjoy!

# Parameters
```
usage: twitch-recorder.py [-h] [-conf CONFIG_FILE] [-cid CLIENT_ID] [-sec CLIENT_SECRET] [-o OAUTH_TOKEN] [-s STREAMER] [-r REFRESH] [-p PATH] [-fix] [-f FFMPEG] [-i IP_ADDRESS] [-ma MAC_ADDRESS] [-m {recorder,watcher}] [-q QUALITY] [-v]

  -h, --help            show this help message and exit
  -conf CONFIG_FILE, --config CONFIG_FILE
  -cid CLIENT_ID, --client-id CLIENT_ID
                        Client ID of the registered Twitch app.
  -sec CLIENT_SECRET, --client-secret CLIENT_SECRET
                        Client secret of the registered Twitch app.
  -o OAUTH_TOKEN, --oauth-token OAUTH_TOKEN
                        OAuth Token to use with registered Twitch app.
  -s STREAMER, --streamer STREAMER
                        Indicate the streamer to watch.
  -r REFRESH, --refresh REFRESH
                        Time between 2 checks.
  -p PATH, --path PATH  Path to save the records.
  -fix, --fix-videos    Fix videos with ffmpeg.
  -f FFMPEG, --ffmpeg FFMPEG
                        Path to the ffmpeg binary.
  -i IP_ADDRESS, --ip-address IP_ADDRESS
                        Recorder IP address.
  -ma MAC_ADDRESS, --mac-address MAC_ADDRESS
                        Recorder MAC address.
  -m {recorder,watcher}, --mode {recorder,watcher}
                        Mode to launch the script.
  -q QUALITY, --quality QUALITY
                        Specify the quality to record (examples: best, worst, audio_only, 720p60, 1080p).
  -v, --verbose         Debug mode.

Args that start with '--' (eg. -cid) can also be set in a config file (twitch-recorder.conf or specified via -conf).
Config file syntax allows: key=value, flag=true.
If an arg is specified in more than one place, then commandline values override config file values which override defaults.
```