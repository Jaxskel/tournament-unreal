import zipfile,pathlib,shutil,time,json
archive=pathlib.Path(r'F:\TournamentUT4\work\UnrealTournament-clean-master.zip')
root=pathlib.Path(r'F:\TournamentUT4\source')
log=pathlib.Path(r'F:\TournamentUT4\work\extract-status.json')
while True:
 try:
  z=zipfile.ZipFile(archive)
  break
 except (FileNotFoundError,zipfile.BadZipFile):time.sleep(5)
items=z.infolist();total=sum(i.file_size for i in items);done=0
for count,item in enumerate(items,1):
 parts=pathlib.PurePosixPath(item.filename)
 if parts.is_absolute() or '..' in parts.parts:raise ValueError('Unsafe path')
 dest=root/pathlib.Path(*parts.parts)
 if item.is_dir():dest.mkdir(parents=True,exist_ok=True)
 else:
  dest.parent.mkdir(parents=True,exist_ok=True)
  with z.open(item) as src,dest.open('wb') as dst:shutil.copyfileobj(src,dst,4*1024*1024)
  done+=item.file_size
 if count%1000==0:log.write_text(json.dumps({'files':count,'totalFiles':len(items),'bytes':done,'totalBytes':total}))
log.write_text(json.dumps({'complete':True,'files':len(items),'bytes':done}))
print('EXTRACT_COMPLETE',done,flush=True)
