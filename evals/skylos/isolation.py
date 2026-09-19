import argparse,importlib.util,tempfile,json
from pathlib import Path
p=Path(__file__).resolve().parents[2]/'rhize-devflow/scripts/skylos_evidence.py'
parser=argparse.ArgumentParser(description='Verify Skylos sandbox isolation with inert temporary sentinel files.')
parser.add_argument('--python',type=Path,required=True)
args=parser.parse_args()
s=importlib.util.spec_from_file_location('adapter',p); a=importlib.util.module_from_spec(s); s.loader.exec_module(a)
worker=r'''
import pathlib,socket,sys,json
source,scratch,outside=map(pathlib.Path,sys.argv[1:])
checks={}
checks['source_read']=source.read_text()=='source sentinel'
for name,action in [('outside_read_denied',lambda: outside.read_text()),('source_write_denied',lambda: source.write_text('changed'))]:
 try: action()
 except PermissionError: checks[name]=True
 else: checks[name]=False
s=socket.socket()
try: s.bind(('127.0.0.1',0))
except PermissionError: checks['network_denied']=True
else: checks['network_denied']=False
finally: s.close()
(scratch/'allowed.txt').write_text('scratch')
checks['scratch_write']=(scratch/'allowed.txt').read_text()=='scratch'
print(json.dumps(checks))
raise SystemExit(0 if all(checks.values()) else 1)
'''
with tempfile.TemporaryDirectory(prefix='skylos-approved-sentinel-') as d:
 root=Path(d).resolve(); source=root/'source'; source.mkdir(); scratch=root/'scratch'; scratch.mkdir()
 file=source/'sentinel.py'; file.write_text('source sentinel'); outside=root/'outside.txt'; outside.write_text('private sentinel')
 profile=a.sandbox_profile(source,scratch,args.python.absolute().parent.parent.resolve())
 code,out,err=a.run_bounded(['/usr/bin/sandbox-exec','-p',profile,str(args.python),'-I','-c',worker,str(file),str(scratch),str(outside)],cwd=source,env=a.environment(scratch))
 print(json.dumps({'exit_code':code,'stdout':out.decode(),'stderr':err.decode(),'source_unchanged':file.read_text()=='source sentinel'}))
 raise SystemExit(code)
