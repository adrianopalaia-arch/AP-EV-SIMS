"""Small deterministic numerical routines; no fitted transform sees evaluation data."""
import math
import statistics

def solve(matrix, target):
    n=len(target); a=[list(row)+[v] for row,v in zip(matrix,target)]
    for i in range(n):
        pivot=max(range(i,n),key=lambda j:abs(a[j][i]))
        a[i],a[pivot]=a[pivot],a[i]
        if abs(a[i][i])<1e-12: raise ValueError('SINGULAR_DESIGN')
        divisor=a[i][i]; a[i]=[x/divisor for x in a[i]]
        for j in range(n):
            if j==i: continue
            factor=a[j][i]
            a[j]=[x-factor*y for x,y in zip(a[j],a[i])]
    return [a[i][-1] for i in range(n)]

class Ridge:
    def __init__(self,penalty=10):
        if not math.isfinite(penalty) or penalty<=0: raise ValueError('invalid ridge penalty')
        self.penalty=penalty
    def fit(self,x,y):
        if not x or len(x)!=len(y): raise ValueError('invalid design')
        d=len(x[0])
        if any(len(row)!=d or any(not math.isfinite(v) for v in row) for row in x): raise ValueError('invalid design')
        self.means=[statistics.mean(row[j] for row in x) for j in range(d)]
        self.scales=[statistics.pstdev(row[j] for row in x) or 1 for j in range(d)]
        design=[[1]+[(v-m)/s for v,m,s in zip(row,self.means,self.scales)] for row in x]
        normal=[[sum(row[i]*row[j] for row in design)+(self.penalty if i==j and i else 0) for j in range(d+1)] for i in range(d+1)]
        target=[sum(row[j]*v for row,v in zip(design,y)) for j in range(d+1)]
        self.coefficients=solve(normal,target)
        return self
    def predict(self,x):
        return self.coefficients[0]+sum(c*(v-m)/s for c,v,m,s in zip(self.coefficients[1:],x,self.means,self.scales))
    def contributions(self,names,x):
        return {name:c*(v-m)/s for name,c,v,m,s in zip(names,self.coefficients[1:],x,self.means,self.scales)}
    def state(self): return dict(penalty=self.penalty,means=self.means,scales=self.scales,coefficients=self.coefficients)
    @classmethod
    def from_state(cls,state):
        obj=cls(state['penalty']); obj.means=state['means']; obj.scales=state['scales']; obj.coefficients=state['coefficients']; return obj

def quantile(values,q):
    if not values or not 0<=q<=1: raise ValueError('invalid quantile')
    ordered=sorted(values); position=(len(ordered)-1)*q; i=int(position)
    return ordered[i]+(ordered[min(i+1,len(ordered)-1)]-ordered[i])*(position-i)

def sigmoid(z):
    if z>=0: return 1/(1+math.exp(-z))
    e=math.exp(z); return e/(1+e)

def clip(p): return min(1-1e-9,max(1e-9,p))

def wilson_lower(wins,n,z=1.645):
    if n<=0: return 0.0
    p=wins/n
    return max(0,(p+z*z/(2*n)-z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/(1+z*z/n))
