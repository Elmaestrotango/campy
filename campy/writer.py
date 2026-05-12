"""
"""
import subprocess
import os, sys, time, logging
from imageio_ffmpeg import get_ffmpeg_exe
from campy.utils.utils import QueueKeyboardInterrupt

PIPE_BUFSIZE = 4 * 1024 * 1024

def OpenWriter(cam_params, queue):
	try:
		writing = False
		folder_name = os.path.join(cam_params["videoFolder"], cam_params["cameraName"])
		file_name = cam_params["videoFilename"]
		full_file_name = os.path.join(folder_name, file_name)

		if not os.path.isdir(folder_name):
			os.makedirs(folder_name)
			print("Made directory {}.".format(folder_name))

		if cam_params["pixelFormatInput"] == "bayer_bggr8" and cam_params["cameraMake"] == "flir":
			cam_params["pixelFormatInput"] == "bayer_rggb8"

		pix_fmt_out = cam_params["pixelFormatOutput"]
		codec = str(cam_params["codec"])
		quality = str(cam_params["quality"])
		preset = str(cam_params["preset"])
		frameRate = str(cam_params["frameRate"])
		gpuID = str(cam_params["gpuID"])
		w = cam_params["frameWidth"]
		h = cam_params["frameHeight"]
		pix_fmt_in = cam_params["pixelFormatInput"]

		gpu_params = []

		if cam_params["gpuID"] == -1:
			print("Opened: {} using CPU to compress the stream.".format(full_file_name))
			if preset == "None":
				preset = "fast"
			gpu_params = [
				"-preset", preset,
				"-tune", "fastdecode",
				"-crf", quality,
				"-bufsize", "20M",
				"-maxrate", "10M",
				"-bf:v", "4",
				]
			if pix_fmt_out == "rgb0" or pix_fmt_out == "bgr0":
				pix_fmt_out = "yuv420p"
			if cam_params["codec"] == "h264":
				codec = "libx264"
				gpu_params.append("-x264-params")
				gpu_params.append("nal-hrd=cbr")
			elif cam_params["codec"] == "h265":
				codec = "libx265"
		else:
			print("Opened: {} using GPU {} to compress the stream.".format(full_file_name, cam_params["gpuID"]))
			if cam_params["gpuMake"] == "nvidia":
				if preset == "None":
					preset = "fast"
				gpu_params = [
					"-preset", preset,
					"-qp", quality,
					"-bf:v", "0",
					"-gpu", gpuID,
					]
				if cam_params["codec"] == "h264":
					codec = "h264_nvenc"
				elif cam_params["codec"] == "h265":
					codec = "hevc_nvenc"
			elif cam_params["gpuMake"] == "amd":
				gpu_params = [
					"-usage", "lowlatency",
					"-rc", "cqp",
					"-qp_i", quality,
					"-qp_p", quality,
					"-qp_b", quality,
					"-bf:v", "0",
					"-hwaccel_device", gpuID,]
				if pix_fmt_out == "rgb0" or pix_fmt_out == "bgr0":
					pix_fmt_out = "yuv420p"
				if cam_params["codec"] == "h264":
					codec = "h264_amf"
				elif cam_params["codec"] == "h265":
					codec = "hevc_amf"
			elif cam_params["gpuMake"] == "intel":
				if preset == "None":
					preset = "faster"
				gpu_params = [
						"-bf:v", "0",
						"-preset", preset,
						"-q", str(int(quality)+1),]
				if pix_fmt_out == "rgb0" or pix_fmt_out == "bgr0":
					pix_fmt_out = "nv12"
				if cam_params["codec"] == "h264":
					codec = "h264_qsv"
				elif cam_params["codec"] == "h265":
					codec = "hevc_qsv"

	except Exception as e:
		logging.error("Caught exception at writer.py OpenWriter: {}".format(e))
		raise

	cmd = [
		get_ffmpeg_exe(),
		"-y",
		"-f", "rawvideo",
		"-vcodec", "rawvideo",
		"-s", "{}x{}".format(w, h),
		"-pix_fmt", pix_fmt_in,
		"-r", frameRate,
		"-an",
		"-i", "-",
		"-vcodec", codec,
		"-pix_fmt", pix_fmt_out,
		"-r", frameRate,
	] + gpu_params + [
		"-loglevel", cam_params["ffmpegLogLevel"],
		full_file_name,
	]

	proc = subprocess.Popen(
		cmd,
		stdin=subprocess.PIPE,
		stdout=subprocess.DEVNULL,
		stderr=subprocess.PIPE,
		bufsize=PIPE_BUFSIZE,
	)
	writing = True

	readQueue = {}
	readQueue["queue"] = queue
	readQueue["message"] = "STOP"

	return proc, writing, readQueue

def WriteFrames(cam_params, writeQueue, stopReadQueue, stopWriteQueue):
	proc, writing, readQueue = OpenWriter(cam_params, stopReadQueue)
	fd = proc.stdin.fileno()

	with QueueKeyboardInterrupt(readQueue):
		while(writing):
			if writeQueue:
				os.write(fd, writeQueue.popleft())
			else:
				if stopWriteQueue:
					writing = False
				time.sleep(0.01)

	print("Closing video writer for {}. Please wait...".format(cam_params["cameraName"]))
	proc.stdin.close()
	proc.wait(timeout=10)
    

