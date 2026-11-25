"""Exact BRep interference and exported STL manifold checks for FH Edge v2."""
import json, struct
from pathlib import Path
from collections import Counter
import numpy as np
import cadquery as cq

ROOT=Path(__file__).resolve().parent
def read(name):return cq.Shape.importBrep(str(ROOT/'CAD'/(name+'.brep')))
def volume(s):return sum(t.Volume() for t in s.Solids())
def intersection(a,b):return volume(a.intersect(b))
def stl_check(path):
    data=path.read_bytes(); n=struct.unpack_from('<I',data,80)[0]
    assert len(data)==84+50*n,(path,'not binary STL')
    a=np.frombuffer(data,offset=84,dtype=np.dtype([('normal','<f4',(3,)),('v','<f4',(3,3)),('attr','<u2')]))
    verts,idx=np.unique(np.round(a['v'].reshape(-1,3).astype(float),5),axis=0,return_inverse=True)
    faces=idx.reshape(-1,3)
    edges=np.vstack([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]])
    unordered=np.sort(edges,axis=1);ue,counts=np.unique(unordered,axis=0,return_counts=True)
    parent=np.arange(len(verts))
    def find(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    for x,y in ue:
        x,y=find(x),find(y)
        if x!=y:parent[x]=y
    comps=len(set(find(i) for i in range(len(verts))))
    v=a['v'].astype(float)
    vol=np.einsum('ij,ij->i',v[:,0],np.cross(v[:,1],v[:,2])).sum()/6
    area=np.linalg.norm(np.cross(v[:,1]-v[:,0],v[:,2]-v[:,0]),axis=1)/2
    directed=Counter(map(tuple,edges.tolist()))
    inconsistent=sum(1 for (x,y),cnt in directed.items() if directed[(y,x)]!=cnt)
    return dict(triangles=n,vertices=len(verts),connected_components=comps,
                nonmanifold_edges=int((counts!=2).sum()),degenerate_triangles=int((area<1e-10).sum()),
                inconsistent_directed_edges=inconsistent,signed_volume_mm3=float(vol),
                bounds_mm=[verts.min(axis=0).tolist(),verts.max(axis=0).tolist()])

def main():
    shell=read('fh-edge-kit-shell');base=read('fh-edge-kit-base')
    esp=read('ESP32-C3-positioned');pn=read('PN5180-PCB-envelope-ASSUMED')
    pipes=[read('led_pipe_1'),read('led_pipe_2')]
    results={'brep':{},'interference_volume_mm3':{},'stl':{},'scope':'CAD-only; PN5180 is an assumed envelope. Physical fit, cable boot and optical/RF performance not tested.'}
    for name,s in [('shell',shell),('base',base),('ESP',esp),('PN_envelope',pn),('pipe1',pipes[0]),('pipe2',pipes[1])]:
        results['brep'][name]=dict(valid=s.isValid(),solids=len(s.Solids()),volume_mm3=volume(s))
    pairs=[('shell/base',shell,base),('shell/ESP',shell,esp),('base/ESP',base,esp),('shell/PN_PCB',shell,pn),('base/PN_PCB',base,pn),('ESP/PN_PCB',esp,pn)]
    for name in ('pn_logic','pn_header','pn_back_solder'):
        q=read(name)
        for pnme,part in [('shell',shell),('base',base),('ESP',esp)]:pairs.append((pnme+'/'+name,part,q))
    for i,p in enumerate(pipes):
        for name,s in [('shell',shell),('base',base),('ESP',esp)]:pairs.append((name+'/pipe'+str(i+1),s,p))
    for name,a,b in pairs:
        v=intersection(a,b);results['interference_volume_mm3'][name]=v
        print(name,round(v,9),flush=True)
    for name in ('fh-edge-kit-mark',):
        results['interference_volume_mm3']['shell/'+name]=intersection(shell,read(name))
    for path in sorted((ROOT/'STL').rglob('*.stl')):
        r=stl_check(path);results['stl'][str(path.relative_to(ROOT/'STL'))]=r
        print(path.name,'components',r['connected_components'],'bad_edges',r['nonmanifold_edges'],'degenerate',r['degenerate_triangles'],flush=True)
    results['pass']=all(x['valid'] for x in results['brep'].values()) and all(v<1e-5 for v in results['interference_volume_mm3'].values()) and all(x['nonmanifold_edges']==0 and x['inconsistent_directed_edges']==0 and x['signed_volume_mm3']>0 for x in results['stl'].values())
    (ROOT/'validation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print('PASS',results['pass'],flush=True)
    if not results['pass']:raise SystemExit(2)

if __name__=='__main__':main()
