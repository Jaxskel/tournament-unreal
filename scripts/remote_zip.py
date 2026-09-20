import io, subprocess, hashlib, pathlib, zipfile, json, sys

class RemoteZipIO(io.RawIOBase):
    def __init__(self,url,size,cache):
        self.url,self.size,self.pos=url,size,0
        self.cache=pathlib.Path(cache);self.cache.mkdir(parents=True,exist_ok=True)
    def seekable(self):return True
    def readable(self):return True
    def tell(self):return self.pos
    def seek(self,offset,whence=0):
        self.pos=offset if whence==0 else self.pos+offset if whence==1 else self.size+offset
        if self.pos<0:raise ValueError('negative seek')
        return self.pos
    def read(self,n=-1):
        if n<0:n=self.size-self.pos
        n=min(n,self.size-self.pos)
        if n<=0:return b''
        start=self.pos;end=start+n-1
        key=hashlib.sha256(self.url.encode()).hexdigest()[:12]
        target=self.cache/f'{key}-{start}-{end}'
        if not target.exists():
            tmp=target.with_suffix('.tmp');headers=target.with_suffix('.headers')
            subprocess.run(['curl','--fail','--silent','--show-error','--location','--retry','2','--max-time','120','--max-filesize',str(n),'--range',f'{start}-{end}','--dump-header',str(headers),'--output',str(tmp),self.url],check=True)
            # Never silently accept a whole archive in response to a range request.
            hs=headers.read_text().lower()
            if 'content-range: bytes '+str(start)+'-'+str(end)+'/' not in hs or tmp.stat().st_size!=n:
                tmp.unlink(missing_ok=True);raise IOError('Server did not honor exact byte range')
            tmp.replace(target)
        self.pos+=n
        return target.read_bytes()

def open_remote(url,size,cache='work/ut4-recovery/ranges'):
    return zipfile.ZipFile(RemoteZipIO(url,size,cache))

if __name__=='__main__':
    url,size,out=sys.argv[1],int(sys.argv[2]),pathlib.Path(sys.argv[3])
    with open_remote(url,size) as z:
        entries=[{'name':i.filename,'size':i.file_size,'compressed':i.compress_size,'offset':i.header_offset,'mode':i.external_attr>>16} for i in z.infolist()]
        out.write_text(json.dumps(entries))
        print(json.dumps({'entries':len(entries),'bytes':sum(i['size'] for i in entries),'assets':sum(i['name'].endswith('.uasset') for i in entries),'maps':sum(i['name'].endswith('.umap') for i in entries)}))
        for i in entries:
            if i['name'].endswith(('Build.version','UE4Editor.app/Contents/MacOS/UE4Editor','UE4-Mac-Shipping.app/Contents/MacOS/UE4-Mac-Shipping','UnrealBuildTool.exe','Mono/bin/mono')):print(i)
