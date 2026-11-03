"""Single bounded KIS bridge/proxy attempt; no CDC or automatic reconnect."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

def kis_devices():
    result=[]
    for path in Path('/sys/bus/usb/devices').iterdir():
        def attr(name):
            try:return (path/name).read_text().strip()
            except OSError:return None
        if attr('idVendor')!='05ac' or attr('idProduct')!='1881':continue
        result.append(dict(path=path.name,speed=attr('speed'),version=attr('bcdDevice'),
                           product=attr('product'),busnum=attr('busnum'),devnum=attr('devnum')))
    return sorted(result,key=lambda p:p['path'])

def main():
    parser=argparse.ArgumentParser()
    for name in ('source','manifest','output','kisd','runtime'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--preflight',action='store_true')
    args=parser.parse_args()
    sys.path.insert(0,args.source)
    import serial
    from aura.proxy import UartInterface,AuraProxy
    manifest=json.loads(Path(args.manifest).read_text())
    tag=bytes.fromhex(manifest['tag_hex']);offset=manifest['tag_offset']
    assert tag==b'NEO-KIS-SINGLE-v1\0' and 0<offset<manifest['footprint']-len(tag)
    if args.preflight:
        help_text=subprocess.run([args.kisd,'--help'],check=True,capture_output=True,text=True).stdout
        assert '--link' in help_text and '--once' in help_text
        print(json.dumps(dict(imports=True,devices=kis_devices(),kisd_sha256=hashlib.sha256(Path(args.kisd).read_bytes()).hexdigest())))
        return
    assert os.geteuid()==0
    os.umask(0o022)
    out=Path(args.output);out.mkdir(mode=0o755,exist_ok=False)
    runtime=Path(args.runtime);assert runtime.is_dir()
    link=runtime/'uart';assert not link.exists() and not link.is_symlink()
    events=(out/'events.jsonl').open('x',buffering=1)
    def emit(event,**fields):
        record=dict(event=event,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    monotonic=time.monotonic(),**fields)
        events.write(json.dumps(record)+'\n');events.flush();os.fsync(events.fileno())
        print(json.dumps(record),flush=True)
    def expired(signum,frame):raise TimeoutError('KIS proxy deadline')
    signal.signal(signal.SIGALRM,expired)
    result=dict(enumerated=False,kisd_binding=False,handshake=False,identity=False,
                trial_tag=False,watchdog_armed=False,exit_acknowledged=False)
    device=proxy=ttylog=bridge=None
    bridge_log=(out/'kisd.log').open('x',buffering=1)
    try:
        assert not kis_devices(), 'Unexpected KIS device before the controlled reboot'
        bridge=subprocess.Popen([args.kisd,'--once','--channel','0','--link',str(link)],
            stdout=bridge_log,stderr=subprocess.STDOUT,env={**os.environ,'RUST_LOG':'info'})
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if bridge.poll() is not None:raise RuntimeError('kisd exited before readiness')
            if link.exists() and 'Waiting for device' in (out/'kisd.log').read_text():break
            time.sleep(.05)
        else:raise TimeoutError('kisd PTY readiness deadline')
        emit('ready',pid=os.getpid(),bridge_pid=bridge.pid,pty=str(link),devices=kis_devices())
        (out/'ready.json').write_text(json.dumps(dict(ready=True,pid=os.getpid(),bridge_pid=bridge.pid))+'\n')
        end=time.monotonic()+360;previous=None
        while time.monotonic()<end:
            seen=kis_devices()
            if seen!=previous:emit('devices',devices=seen);previous=seen
            if len(seen)>1:raise RuntimeError('Ambiguous KIS devices')
            if seen:result['enumerated']=True;result['usb_device']=seen[0]
            log=(out/'kisd.log').read_text()
            if 'NEO_KIS_BINDING_OK' in log and 'Device opened' in log:
                result['kisd_binding']=True;break
            if bridge.poll() is not None:raise RuntimeError('KIS bridge failed; see kisd.log')
            if (out/'stop-waiting').exists():raise RuntimeError('Neo returned before KIS connected')
            time.sleep(.05)
        else:raise TimeoutError('No qualified KIS connection within360s')
        signal.alarm(30)
        device=serial.Serial(str(link),115200,timeout=2,write_timeout=2,exclusive=True)
        iface=UartInterface(device)
        ttylog=(out/'console.txt').open('x',buffering=1);iface.tty_log=ttylog
        emit('nop_tx');iface.nop();result['handshake']=True;emit('nop_ok')
        proxy=AuraProxy(iface)
        chip=proxy.get_chipid();result['chip_id']=hex(chip);assert chip==0x8140
        base=proxy.get_base();result['base']=hex(base)
        assert 0x10000000000<=base and base+offset+len(tag)<0x10200000000
        observed=iface.readmem(base+offset,len(tag));assert observed==tag,observed
        result['identity']=result['trial_tag']=True
        emit('trial_identified',tag=tag.rstrip(bytes([0])).decode(),base=hex(base))
        armed=proxy.wdt_arm(90);result['watchdog_return']=armed;assert armed==0
        result['watchdog_armed']=True;emit('watchdog_confirmed',seconds=90)
        result['nop_ms']=[]
        for _ in range(5):
            start=time.monotonic();proxy.nop();result['nop_ms'].append((time.monotonic()-start)*1000)
            time.sleep(.1)
        emit('probe_complete',result=result)
    except Exception as e:
        result['error']=repr(e);emit('error',error=repr(e),traceback=traceback.format_exc())
    finally:
        signal.alarm(0)
        if proxy is not None and result['identity']:
            try:
                signal.alarm(5);emit('exit_tx');proxy.exit()
                result['exit_acknowledged']=True;emit('exit_acknowledged')
                signal.alarm(0)
                device.timeout=.1
                end=time.monotonic()+3
                with (out/'post-exit-console.bin').open('xb') as f:
                    while time.monotonic()<end:f.write(device.read(8192))
            except Exception as e:result['exit_error']=repr(e);emit('exit_error',error=repr(e))
            finally:signal.alarm(0)
        if device is not None:device.close()
        if ttylog is not None:ttylog.close()
        if bridge is not None:
            if bridge.poll() is None:
                bridge.terminate()
                try:bridge.wait(timeout=5)
                except subprocess.TimeoutExpired:bridge.kill();bridge.wait(timeout=5)
            result['bridge_returncode']=bridge.returncode
        bridge_log.close()
        if link.is_symlink():link.unlink()
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        emit('finished',result=result);events.close()
    if not all(result[k] for k in ('enumerated','kisd_binding','handshake','identity','trial_tag','watchdog_armed','exit_acknowledged')):
        raise SystemExit(1)

if __name__=='__main__':main()
