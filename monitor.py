import numpy as np
import time
import datetime
import picamera
import os
import operator
from PIL import Image, ImageDraw, ImageFont
from functools import reduce

def mse(imageA, imageB):
	# the 'Mean Squared Error' between the two images is the
	# sum of the squared difference between the two images;
	# NOTE: the two images must have the same dimension
	err = np.sum((imageA.astype("float") - imageB.astype("float")) ** 2)
	err /= float(imageA.shape[0] * imageA.shape[1])
	# return the MSE, the lower the error, the more "similar"
	# the two images are
	return err

# remove brightness difference
def equalize(im):
    h = im.convert("L").histogram()
    lut = []
    for b in range(0, len(h), 256):
        # step size
        step = reduce(operator.add, h[b:b+256]) / 255
        # create equalization lookup table
        n = 0
        for i in range(256):
            lut.append(n / step)
            n = n + h[i+b]
    # map image through lookup table
    return im.point(lut*im.layers)

def capture():
	currTime = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S_%f"))[:-3].replace(":","-").replace(" ","_")
	camera.capture(currTime+".jpg")
	# current = Image.open("temp.jpg")
	current = Image.open(currTime+".jpg")
	current = equalize(current)
	current = current.convert("L").convert("RGB")
	# drawCurr = ImageDraw.Draw(current)
	# drawCurr.text([0.005 * xSize, 0.005 * ySize],\
	# currTime, fill = (0, 255, 0),font = myFont)
	current.save(currTime+".jpg")
	return currTime+".jpg"

#set gap between each picture
gap = 0

xSize = 640
ySize = 480
camera = picamera.PiCamera()
camera.resolution = (xSize,ySize)

camera.vflip = True
camera.hflip = True
before = datetime.datetime.now()
i = 0
myFont = ImageFont.truetype("/home/pi/fonts/Hack/Hack-Bold.ttf", 16)
sum = 0;
min = 9999
max = 0
minute = 0
keep = False


capture()
time.sleep(1)
while True:
	i += 1
	# time.sleep(gap)

	currName = capture()
	curr = Image.open(currName)
	if(i>1):
		prev = Image.open(prevName)
		err = mse(np.array(curr),np.array(prev))
		currTime = currName[:-4]

		#keep a picture every minute
		# if int(currTime[-5:-3]) == 5 or int(currTime[-5:-3]) == 0 and not keep:
		# 	keep = True
		# else:
		# 	keep = False

		sum += err
		if err < min:
			min = err
		if err > max:
			max = err
		# print(currTime,err,str(sum/i),min,max,sep="\t")

		if err < 350 or i == 2:  # normal
			if not keep:
				# pass
				os.remove(prevName)
		else:
			print(currTime,err,str(sum/i),min,max,sep="\t")
			print("movement detected. Recoding...")
			camera.resolution = (640,480)
			camera.framerate = 30
			camera.start_recording(currTime.replace(":","-").replace(" ","_")+'.h264')
			camera.wait_recording(20)
			camera.stop_recording()
			camera.resolution = (xSize,ySize)
			i += 1
			currName = capture()
	prevName = currName

after = datetime.datetime.now()
total = after - before
print(total)