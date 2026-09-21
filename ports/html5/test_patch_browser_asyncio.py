"""Original bounded fixtures and optional private actual-body AsyncIO tests.

python3 -B ports/html5/test_patch_browser_asyncio.py
ASYNCIO_ACTUAL_SOURCE=/private/AsyncIOSystemBase.cpp also executes its patched
producer body in instrumented C++ stubs. No engine, Windows write or build.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest

PATCHER = runpy.run_path(str(Path(__file__).with_name('patch-browser-asyncio.py')))
SOURCE = '''uint64 FAsyncIOSystemBase::QueueDestroyHandleRequest(const FString& FileName)
{
    FScopeLock ScopeLock(CriticalSection);
    FAsyncIORequest IORequest;
    IORequest.RequestIndex = RequestIndex++;
    IORequest.FileName = FileName;
    IORequest.FileNameHash = FCrc::StrCrc32<TCHAR>(*FileName.ToLower());
    IORequest.Priority = AIOP_MIN;
    IORequest.bIsDestroyHandleRequest = true;
    if (GbLogAsyncLoading == true) { LogIORequest(TEXT("fixture hint"), IORequest); }
    OutstandingRequests.Add(IORequest);
    OutstandingRequestsEvent->Trigger();
    return IORequest.RequestIndex;
}
uint64 FAsyncIOSystemBase::QueueIORequest()
{
    FScopeLock ScopeLock(CriticalSection);
    FAsyncIORequest IORequest;
    OutstandingRequests.Add(IORequest);
    return 1;
}
void Unrelated() { UE_LOG(LogStreaming, Error, TEXT("Keep diagnostics")); }
'''
STUBS = r'''
#include <cassert>
#include <cctype>
#include <cstdint>
#include <string>
#include <vector>
#include <mutex>
using uint64=uint64_t; using uint32=uint32_t; using TCHAR=char;
#define TEXT(x) x
const int AIOP_MIN=0;
struct FString {
 std::string value;
 FString(const char* v=""):value(v){}
 FString ToLower() const { FString s=*this; for(char& c:s.value)c=std::tolower(static_cast<unsigned char>(c));return s; }
 const char* operator*()const{return value.c_str();}
};
struct FCrc { template<class T>static uint32 StrCrc32(const T* s){uint32 h=0;while(*s)h=h*31+*s++;return h;} };
struct FPlatformProcess {static bool threaded;static bool SupportsMultithreading(){return threaded;}};
bool FPlatformProcess::threaded=false;
static int lockDepth=0;
struct FScopeLock {std::recursive_mutex* mutex;explicit FScopeLock(std::recursive_mutex* m):mutex(m){mutex->lock();++lockDepth;}~FScopeLock(){--lockDepth;mutex->unlock();}};
struct FAsyncIORequest {uint64 RequestIndex=0;FString FileName;uint32 FileNameHash=0;int Priority=0;bool bIsDestroyHandleRequest=false;};
struct Queue {
 std::vector<FAsyncIORequest> items;
 void Add(const FAsyncIORequest& r){assert(lockDepth==1);items.push_back(r);}
 std::vector<FAsyncIORequest>::const_iterator begin()const{assert(lockDepth==1);return items.begin();}
 std::vector<FAsyncIORequest>::const_iterator end()const{return items.end();}
};
struct Counter {int value=0;int GetValue()const{assert(lockDepth==1);return value;}};
struct Event {int calls=0;void Trigger(){assert(lockDepth==1);++calls;}};
struct FAsyncIOSystemBase {
 std::recursive_mutex mutex;std::recursive_mutex* CriticalSection=&mutex;
 Counter BusyWithRequest;Queue OutstandingRequests;Event event;Event* OutstandingRequestsEvent=&event;
 uint64 RequestIndex=1;bool GbLogAsyncLoading=true;int logs=0,cacheLookups=0;std::vector<uint32> cached;
 void LogIORequest(const char*,const FAsyncIORequest&){assert(lockDepth==1);++logs;}
 void* FindCachedFileHandle(uint32 hash){assert(lockDepth==1);++cacheLookups;for(uint32 h:cached)if(h==hash)return this;return nullptr;}
 uint64 QueueDestroyHandleRequest(const FString& FileName);
 void pending(const char* file,bool destroy=false){FAsyncIORequest r;r.FileName=file;r.FileNameHash=FCrc::StrCrc32<TCHAR>(*r.FileName.ToLower());r.bIsDestroyHandleRequest=destroy;OutstandingRequests.items.push_back(r);}
};
'''
MAIN = r'''
int main(){
 const uint32 hash=FCrc::StrCrc32<TCHAR>(*FString("File").ToLower());
 for(int threaded=0;threaded<2;++threaded){
  FPlatformProcess::threaded=threaded;
  const bool shortcut=PLATFORM_HTML5_BROWSER&&!threaded;
  FAsyncIOSystemBase empty;
  for(int i=0;i<4464;++i)assert(empty.QueueDestroyHandleRequest("File")== (shortcut?0:static_cast<uint64>(i+1)));
  assert(empty.OutstandingRequests.items.size()==(shortcut?0:4464));
  assert(empty.event.calls==(shortcut?0:4464));assert(empty.logs==empty.event.calls);
  assert(empty.RequestIndex==(shortcut?1:4465));
  if(!shortcut)assert(empty.cacheLookups==0);
  FAsyncIOSystemBase cached;cached.cached.push_back(hash);
  assert(cached.QueueDestroyHandleRequest("FILE")==1);assert(cached.event.calls==1);
  FAsyncIOSystemBase pending;pending.pending("file");
  assert(pending.QueueDestroyHandleRequest("FILE")==1);assert(pending.OutstandingRequests.items.size()==2);
  assert(!pending.OutstandingRequests.items[0].bIsDestroyHandleRequest);
  assert(pending.OutstandingRequests.items[1].bIsDestroyHandleRequest);
  FAsyncIOSystemBase unrelated;unrelated.pending("Other");unrelated.pending("file",true);
  assert(unrelated.QueueDestroyHandleRequest("File")==static_cast<uint64>(shortcut?0:1));
  assert(unrelated.OutstandingRequests.items.size()==(shortcut?2:3));
  FAsyncIOSystemBase active;active.BusyWithRequest.value=1;
  assert(active.QueueDestroyHandleRequest("File")==1);assert(active.cacheLookups==0);
  FAsyncIOSystemBase after;
  assert(after.QueueDestroyHandleRequest("File")==static_cast<uint64>(shortcut?0:1));
  after.pending("file"); // A later producer still gets its own required close hint.
  assert(after.QueueDestroyHandleRequest("file")==static_cast<uint64>(shortcut?1:2));
  assert(after.OutstandingRequests.items.back().bIsDestroyHandleRequest);
  assert(lockDepth==0);
 }
}
'''

class AsyncIOTests(unittest.TestCase):
    def test_insertion_only_and_idempotent_lf_crlf(self):
        for newline in ('\n','\r\n'):
            source=SOURCE.replace('\n',newline)
            updated=PATCHER['transform'](source)
            insertion=''.join('    '+line+newline for line in PATCHER['INSERT'].splitlines())
            self.assertEqual(updated.replace(insertion,'',1),source)
            self.assertEqual(PATCHER['transform'](updated),updated)
            self.assertEqual(updated.count('UE_LOG(LogStreaming, Error'),1)

    def test_unknown_producer_lock_and_modified_guards_rejected(self):
        patched=PATCHER['transform'](SOURCE)
        variants=[SOURCE.replace('FScopeLock ScopeLock(CriticalSection);','',1),
                  SOURCE.replace('OutstandingRequests.Add(IORequest);','OtherQueue.Add(IORequest);'),
                  SOURCE.replace('uint64 FAsyncIOSystemBase::QueueIORequest()', 'uint64 FAsyncIOSystemBase::Different()'),
                  patched.replace('BusyWithRequest.GetValue() == 0','BusyWithRequest.GetValue() >= 0'),
                  SOURCE+SOURCE]
        for text in variants:
            with self.subTest(text=text),self.assertRaises(ValueError):PATCHER['transform'](text)

    def test_crlf_insertion_does_not_consume_first_unindented_token(self):
        source=SOURCE.replace('    FAsyncIORequest IORequest;', 'FAsyncIORequest IORequest;').replace('\n','\r\n')
        updated=PATCHER['transform'](source)
        self.assertIn('    #endif\r\nFAsyncIORequest IORequest;',updated)
        self.assertEqual(PATCHER['transform'](updated),updated)

    def test_private_backup_readonly_and_repeat_apply(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();(root/'.tournament-browser-port').touch()
            version=root/'Engine/Build/Build.version';version.parent.mkdir(parents=True)
            version.write_text(json.dumps(dict(MajorVersion=4,MinorVersion=15,PatchVersion=0,Changelist=3228288)))
            path=root/PATCHER['SOURCE_PATH'];path.parent.mkdir(parents=True)
            original=b'\xef\xbb\xbf'+SOURCE.replace('\n','\r\n').encode();path.write_bytes(original)
            backup=Path(str(path)+PATCHER['BACKUP_SUFFIX'])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(PATCHER['patch'](root)['status'],'would-patch')
                self.assertEqual(path.read_bytes(),original);self.assertFalse(backup.exists())
                PATCHER['patch'](root,True)
                self.assertEqual(backup.read_bytes(),original)
                before=(path.read_bytes(),path.stat().st_mtime_ns,backup.stat().st_mtime_ns)
                self.assertEqual(PATCHER['patch'](root,True)['status'],'already-patched')
                self.assertEqual(before,(path.read_bytes(),path.stat().st_mtime_ns,backup.stat().st_mtime_ns))
                backup.write_bytes(b'unknown backup')
                with self.assertRaises(ValueError):PATCHER['patch'](root,True)
                self.assertEqual(path.read_bytes(),before[0])

    def execute_body(self,source):
        compiler=shutil.which('clang++') or shutil.which('g++')
        self.assertIsNotNone(compiler,'A C++ compiler is required for producer-body tests')
        transformed=PATCHER['transform'](source)
        left,right=PATCHER['method_span'](transformed,'QueueDestroyHandleRequest')
        body='uint64 FAsyncIOSystemBase::QueueDestroyHandleRequest(const FString& FileName)'+transformed[left:right]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);cpp=root/'test.cpp';cpp.write_text(STUBS+body+MAIN)
            for browser in (0,1):
                binary=root/('test'+str(browser))
                subprocess.run([compiler,'-std=c++11','-Wall','-Wextra','-Werror',f'-DPLATFORM_HTML5_BROWSER={browser}',str(cpp),'-o',str(binary)],check=True,capture_output=True,text=True)
                subprocess.run([str(binary)],check=True,timeout=10)

    def test_compiled_original_fixture_browser_native_and_threaded_paths(self):self.execute_body(SOURCE)

    @unittest.skipUnless(os.environ.get('ASYNCIO_ACTUAL_SOURCE'),'Set ASYNCIO_ACTUAL_SOURCE for private actual-body validation')
    def test_private_actual_body(self):self.execute_body(Path(os.environ['ASYNCIO_ACTUAL_SOURCE']).read_text())

if __name__=='__main__':unittest.main(verbosity=2)
