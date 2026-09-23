import time
from collections import defaultdict, deque

class RateLimiter:
    def __init__(self): self.events=defaultdict(deque)
    def check(self,key,limit,window=60):
        now=time.monotonic(); key=(key,window)
        if len(self.events)>=5000:
            self.events=defaultdict(deque,{k:v for k,v in self.events.items() if v and v[-1]>now-k[1]})
            if key not in self.events and len(self.events)>=5000:return window
        q=self.events[key]
        while q and q[0]<=now-window: q.popleft()
        if len(q)>=limit: return max(1,int(window-(now-q[0]))+1)
        q.append(now)
        return 0
