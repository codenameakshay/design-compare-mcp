import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path('/Users/codenameakshay/Development/codenameakshay/design-compare-mcp')
OUT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'worker'))
from vision_worker.metrics import color as current

def load(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

v1 = load('v1',Path('/tmp/dcm-color-source-scaled-implementation/v1_color.py'))
old = load('rejected',Path('/tmp/dcm-color-continuous-implementation/rejected_color.py'))
rows = []
for count in (100,200,400,600,800):
    a = np.repeat(np.array([(255,29,255),(35,136,71)],dtype=np.uint8),[8000-count,count],axis=0)[None]
    b = np.repeat(np.array([(255,29,255),(53,133,76)],dtype=np.uint8),[8000-count,count],axis=0)[None]
    row = {'fraction':count/8000}
    for name,module in [('v2',current),('v1',v1),('rejected',old)]:
        score,findings,m = module.color_score(a,b)
        row[name] = {'score':score,'types':[f['type'] for f in findings],'measurements':m}
    rows.append(row)
(OUT/'reversal.json').write_text(json.dumps(rows,indent=2))
print(json.dumps([{k:v if k=='fraction' else {'score':v['score'],'types':v['types']} for k,v in row.items()} for row in rows]))
