"""Same-directory atomic journal writes; retry file locks, never DB requests."""
import json
import os
import time
from uuid import uuid4


def save(path, report):
    temporary=path.with_name(path.name+'.'+uuid4().hex+'.pending')
    # Unique file avoids contention on the former shared .tmp filename.
    with temporary.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    for attempt in range(3):
        try:
            os.replace(temporary,path)
            return
        except PermissionError as exc:
            if attempt==2:
                # Preserve both old journal and complete new checkpoint; no deletion.
                print(json.dumps({'stage':'LOCAL_JOURNAL_REPLACE','error_type':'PermissionError',
                                  'errno':exc.errno,'winerror':getattr(exc,'winerror',None),
                                  'checkpoint':temporary.name,'rpc_retry':False}))
                raise
            time.sleep(0.05*(attempt+1))
