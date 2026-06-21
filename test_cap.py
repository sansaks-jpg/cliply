import cv2
import time
import os

# Create a dummy video
out = cv2.VideoWriter('dummy.mp4', cv2.VideoWriter_fourcc(*'mp4v'), 30, (640, 480))
for i in range(300):
    out.write(cv2.imread('frontend/src/app/globals.css') if False else cv2.imread('package.json') if False else __import__('numpy').zeros((480, 640, 3), dtype=__import__('numpy').uint8))
out.release()

def test_read():
    cap = cv2.VideoCapture('dummy.mp4')
    t0 = time.time()
    for i in range(300):
        ret, frame = cap.read()
        if i % 7 == 0:
            pass
    print("read:", time.time() - t0)

def test_grab():
    cap = cv2.VideoCapture('dummy.mp4')
    t0 = time.time()
    for i in range(300):
        ret = cap.grab()
        if i % 7 == 0:
            ret, frame = cap.retrieve()
    print("grab:", time.time() - t0)

test_read()
test_grab()
