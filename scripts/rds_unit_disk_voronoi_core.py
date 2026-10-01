"""Exact rational-site coverage of the entire closed unit disk.

Half-plane clipping certifies every interior truncated Voronoi vertex. All
pair bisector/circle intersections, boundary stationary points and (1,0)
certify the boundary via the finite-extrema lemma. Floating point selects a
proposed coverer only; every accepted distance inequality is rational/radical
and exact. Frozen replay uses the recorded coverer and no floating selection.
No global-optimality claim is made.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)


def sha(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def rational(value):
    if not isinstance(value,(str,int)) or isinstance(value,bool) or len(str(value))>160:
        raise ValueError('Expected bounded rational string or integer')
    return F(value)


def radical_le_zero(a,b,d):
    """a+b*sqrt(d)<=0, d>=0; exactly two rational sign/square tests."""
    if d<0:
        raise ValueError('negative radicand')
    if b==0 or d==0:
        return a<=0
    if b>0:
        return a<=0 and b*b*d<=a*a
    return a<=0 or a*a<=b*b*d


def clip(poly,a,b,h):
    if not poly:
        return []
    result=[]
    p=poly[-1]
    fp=h-a*p[0]-b*p[1]
    for q in poly:
        fq=h-a*q[0]-b*q[1]
        if (fp>=0)!=(fq>=0):
            lam=fp/(fp-fq)
            result.append((p[0]+lam*(q[0]-p[0]),p[1]+lam*(q[1]-p[1])))
        if fq>=0:
            result.append(q)
        p,fp=q,fq
    clean=[]
    for p in result:
        if not clean or p!=clean[-1]:
            clean.append(p)
    if len(clean)>1 and clean[0]==clean[-1]:
        clean.pop()
    return clean


def compute(spec,frozen=None):
    if spec.get('schema')!=1 or spec.get('kind')!='unit_disk_cover':
        raise ValueError('Expected schema1 unit_disk_cover')
    raw=spec.get('centers')
    if not isinstance(raw,list) or not 1<=len(raw)<=256:
        raise ValueError('1..256 centers required')
    centers=[]
    for row in raw:
        if not isinstance(row,list) or len(row)!=2:
            raise ValueError('two coordinates required')
        center=tuple(map(rational,row))
        if any(abs(x)>8 for x in center):
            raise ValueError('coordinate range exceeds supported verifier bounds')
        if center not in centers:
            centers.append(center)
    radius2=rational(spec.get('radius_squared'))
    if not 0<=radius2<=64:
        raise ValueError('invalid supported squared radius')
    norms=[x*x+y*y for x,y in centers]
    interior=[]
    for i,(cx,cy) in enumerate(centers):
        poly=[(F(-1),F(-1)),(F(1),F(-1)),(F(1),F(1)),(F(-1),F(1))]
        for j,(dx,dy) in enumerate(centers):
            if i!=j:
                poly=clip(poly,dx-cx,dy-cy,(norms[j]-norms[i])/2)
        for x,y in poly:
            if x*x+y*y<=1:
                dist=(x-cx)**2+(y-cy)**2
                if dist>radius2:
                    return {'verdict':'refuted','reason':'uncovered exact Voronoi vertex',
                            'point':[str(x),str(y)],'nearest_center':i,
                            'distance_squared':str(dist),'radius_squared':str(radius2)}
                interior.append([i,str(x),str(y)])
    recorded=[]
    frozen_rows=frozen.get('boundary_checks') if frozen is not None else None
    if frozen is not None and not isinstance(frozen_rows,list):
        raise ValueError('frozen boundary rows required')
    floats=[tuple(map(float,c)) for c in centers] if frozen is None else None

    def boundary(label,px,py,qx,qy,d):
        # The unit-circle point is (px+qx*sqrt(d),py+qy*sqrt(d)).
        def covered(owner):
            cx,cy=centers[owner]
            a=1+norms[owner]-2*(cx*px+cy*py)-radius2
            b=-2*(cx*qx+cy*qy)
            return radical_le_zero(a,b,d)
        if frozen is not None:
            index=len(recorded)
            if index>=len(frozen_rows):
                raise ValueError('missing boundary row')
            row=frozen_rows[index]
            if (not isinstance(row,list) or len(row)!=len(label)+1 or row[:-1]!=label
                    or type(row[-1]) is not int or not 0<=row[-1]<len(centers)):
                raise ValueError('changed boundary identity or coverer')
            owner=row[-1]
            if not covered(owner):
                raise ValueError('frozen coverer fails exact distance test')
        else:
            root=math.sqrt(float(d))
            x,y=float(px)+float(qx)*root,float(py)+float(qy)*root
            owner=min(range(len(centers)),key=lambda j:(x-floats[j][0])**2+(y-floats[j][1])**2)
            if not covered(owner):
                owner=next((j for j in range(len(centers)) if covered(j)),None)
                if owner is None:
                    raise UncoveredBoundary({'label':label,'point':[[str(px),str(qx)],[str(py),str(qy)]],
                                              'radicand':str(d),'radius_squared':str(radius2)})
        recorded.append(label+[owner])

    try:
        boundary(['fixed'],F(1),F(0),F(0),F(0),F(0))
        for i,(x,y) in enumerate(centers):
            if norms[i]>0:
                boundary(['antipodal',i],F(0),F(0),-x/norms[i],-y/norms[i],norms[i])
        for i,(cx,cy) in enumerate(centers):
            for j in range(i+1,len(centers)):
                dx,dy=centers[j][0]-cx,centers[j][1]-cy
                v2=dx*dx+dy*dy
                h=(norms[j]-norms[i])/2
                d=v2-h*h
                if d>=0:
                    for sign in (-1,1):
                        boundary(['bisector',i,j,sign],h*dx/v2,h*dy/v2,
                                 -sign*dy/v2,sign*dx/v2,d)
    except UncoveredBoundary as e:
        return {'verdict':'refuted','reason':'uncovered exact unit-circle point','witness':e.args[0]}
    if frozen is not None and len(recorded)!=len(frozen_rows):
        raise ValueError('extra boundary rows')
    result={'schema':1,'kind':'rational_voronoi_unit_disk_cover','verdict':'pass',
            'semantics':'whole_closed_unit_disk_coverage_only_no_global_optimality',
            'input_sha256':sha(spec),'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'center_count':len(raw),'distinct_center_count':len(centers),
            'radius_squared':str(radius2),'interior_voronoi_vertices':interior,
            'boundary_checks':recorded,
            'sufficiency':'exact halfplane Voronoi clipping plus complete circle extrema; see proof document'}
    if frozen is not None and frozen!=result:
        raise ValueError('frozen certificate differs from complete exact replay')
    return result


class UncoveredBoundary(Exception):
    pass


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--spec',required=True)
    parser.add_argument('--certificate')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    spec=json.loads(Path(args.spec).read_text(encoding='utf-8'))
    frozen=json.loads(Path(args.certificate).read_text(encoding='utf-8')) if args.certificate else None
    result=compute(spec,frozen)
    Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'verdict':result['verdict'],'output':str(Path(args.output).resolve()),
                      'semantics':result.get('semantics'),'boundary_checks':len(result.get('boundary_checks',[])),
                      'interior_vertices':len(result.get('interior_voronoi_vertices',[]))}))
    if result['verdict']!='pass':
        raise SystemExit(2)
