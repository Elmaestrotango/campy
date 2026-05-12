"""
CamPy: Python-based multi-camera recording software.
Writes raw frames to disk during acquisition, then encodes to H.264 via NVENC post-hoc.

Usage:
campy-acquire ./configs/campy_config.yaml
"""

import os, time, sys, logging, threading
from collections import deque
import multiprocessing as mp
from campy import writer, display, configurator
from campy.trigger import trigger
from campy.cameras import unicam
from campy.utils.utils import HandleKeyboardInterrupt

def OpenSystems():
	params = configurator.ConfigureParams()
	systems = unicam.LoadSystems(params)
	systems = unicam.GetDeviceList(systems, params)
	systems = trigger.StartTriggers(systems, params)
	return systems, params


def CloseSystems(systems, params):
	trigger.StopTriggers(systems, params)
	unicam.CloseSystems(systems, params)


def AcquireOneCamera(n_cam):
	cam_params = configurator.ConfigureCamParams(systems, params, n_cam)

	dispQueue = deque([], 2)
	writeQueue = deque()
	stopReadQueue = deque([],1)
	stopWriteQueue = deque([],1)

	# Raw file for this camera
	folder_name = os.path.join(cam_params["videoFolder"], cam_params["cameraName"])
	if not os.path.isdir(folder_name):
		os.makedirs(folder_name)
	raw_path = os.path.join(folder_name, "raw.bin")
	raw_fd = os.open(raw_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_BINARY)

	# Writer thread: drain writeQueue to raw file
	def raw_writer():
		from campy.utils.utils import QueueKeyboardInterrupt
		readQueue = {"queue": stopReadQueue, "message": "STOP"}
		with QueueKeyboardInterrupt(readQueue):
			while True:
				if writeQueue:
					os.write(raw_fd, writeQueue.popleft())
				elif stopWriteQueue:
					break
				else:
					time.sleep(0.001)
		os.close(raw_fd)

	threading.Thread(
		target=display.DisplayFrames,
		daemon=True,
		args=(cam_params, dispQueue,),
	).start()

	threading.Thread(
		target=unicam.GrabFrames,
		daemon=True,
		args=(cam_params, writeQueue, dispQueue, stopReadQueue, stopWriteQueue,),
	).start()

	raw_writer()


def Main():
	with HandleKeyboardInterrupt():
		p = mp.get_context("spawn").Pool(params["numCams"])
		p.map_async(AcquireOneCamera, range(params["numCams"])).get()

	CloseSystems(systems, params)

systems, params = OpenSystems()