"""TrimUI hardware test: python3 measure_trimui_input.py

Writes D-pad events and returns to the three-host overview. Measures event-to-active
SDL framebuffer repaint, not optical LCD latency. Target: under 250 ms.
Requires this Smart Pro S firmware's DRM debugfs and PRIME DMA-BUF support.
"""
import ctypes as C,fcntl,json,mmap,os,struct,time,urllib.request
from pathlib import Path
import re
text=Path('/sys/kernel/debug/dri/0/state').read_text()
target=None
for block in re.split(r'(?m)^plane\[',text)[1:]:
    block=block.split('\ncrtc[',1)[0]
    owner=re.search(r'allocated by = (.+)',block)
    fb=re.search(r'\n\s*fb=(\d+)',block)
    crtc=re.search(r'\n\s*crtc=(.+)',block)
    if owner and owner[1].strip()=='python3' and fb and int(fb[1]) and crtc and crtc[1]!='(null)':
        target={'plane':int(block.split(']',1)[0])}
        break
assert target, 'Start the TrimUI SDL dashboard before measuring'
class FB2(C.Structure):
    _fields_=[('fb_id',C.c_uint32),('width',C.c_uint32),('height',C.c_uint32),('pixel_format',C.c_uint32),('modifier',C.c_uint64),('flags',C.c_uint32),('handles',C.c_uint32*4),('pitches',C.c_uint32*4),('offsets',C.c_uint32*4)]
drm=C.CDLL('libdrm.so.2',use_errno=True)
drm.drmModeGetFB2.argtypes=[C.c_int,C.c_uint32];drm.drmModeGetFB2.restype=C.POINTER(FB2)
drm.drmModeFreeFB2.argtypes=[C.POINTER(FB2)]
fd=os.open('/dev/dri/card0',os.O_RDWR)
class Plane(C.Structure):
 _fields_=[('count_formats',C.c_uint32),('formats',C.POINTER(C.c_uint32)),('plane_id',C.c_uint32),('crtc_id',C.c_uint32),('fb_id',C.c_uint32),('possible_crtcs',C.c_uint32),('gamma_size',C.c_uint32)]
drm.drmModeGetPlane.argtypes=[C.c_int,C.c_uint32];drm.drmModeGetPlane.restype=C.POINTER(Plane)
drm.drmModeFreePlane.argtypes=[C.POINTER(Plane)]
drm.drmPrimeHandleToFD.argtypes=[C.c_int,C.c_uint32,C.c_uint32,C.POINTER(C.c_int)]
cache={}
def pixel(y):
 plane=drm.drmModeGetPlane(fd,target['plane']);assert plane
 fid=plane.contents.fb_id;drm.drmModeFreePlane(plane)
 if fid not in cache:
  fb=drm.drmModeGetFB2(fd,fid);assert fb
  g=fb.contents;prime=C.c_int(-1)
  assert g.width==1280 and g.height==720 and g.modifier==0 and g.offsets[0]==0 and g.pixel_format==int.from_bytes(b'XR24','little'), 'Unexpected SDL framebuffer layout'
  assert drm.drmPrimeHandleToFD(fd,g.handles[0],os.O_CLOEXEC|os.O_RDWR,C.byref(prime))==0,C.get_errno()
  cache[fid]=(prime.value,mmap.mmap(prime.value,g.pitches[0]*g.height,mmap.MAP_SHARED,mmap.PROT_READ),g.pitches[0])
  drm.drmModeFreeFB2(fb)
 p,mem,pitch=cache[fid]
 fcntl.ioctl(p,0x40086200,struct.pack('Q',1))
 value=tuple(mem[y*pitch+30*4:y*pitch+30*4+3])
 fcntl.ioctl(p,0x40086200,struct.pack('Q',5))
 return value
def state():return json.load(urllib.request.urlopen('http://127.0.0.1:8766/status',timeout=2))
def control(a):urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8766/control',data=json.dumps({'action':a}).encode(),headers={'Content-Type':'application/json'}),timeout=2).close()
control('back');control('back');time.sleep(.8)
node=next(p.name for p in Path('/sys/class/input').glob('event*') if (p/'device/name').read_text().strip()=='TRIMUI Player1')
event=os.open('/dev/input/'+node,os.O_WRONLY)
samples=[]
try:
 for n in range(5):
  st=state();assert st['device']['name']=='TrimUI' and not st['detail'] and len(st['hosts'])==3, 'Use the TrimUI three-host overview'
  index=[h['host'] for h in st['hosts']].index(st['selected']);y=[200,386,572][index]
  before=pixel(y);start=time.monotonic()
  for value in (1,0):os.write(event,struct.pack('@llHHi',0,0,3,17,value)+struct.pack('@llHHi',0,0,0,0,0))
  while sum(abs(a-b) for a,b in zip(pixel(y),before))<30:
   assert time.monotonic()-start<5,'No selection repaint within 5 seconds'
   time.sleep(.005)
  samples.append(round((time.monotonic()-start)*1000,1));time.sleep(.2)
 print(json.dumps({'input_to_sdl_scanout_ms':samples,'max_ms':max(samples)}),flush=True)
 assert max(samples)<500,'Direction input repaint exceeds 500 ms'
finally:
 os.close(event)
 for p,mem,_ in cache.values():mem.close();os.close(p)
 os.close(fd)
