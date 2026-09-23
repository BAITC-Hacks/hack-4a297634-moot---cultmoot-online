import time
from collections import defaultdict, deque

class RateLimiter:
    def __init__(self): self.events=defaultdict(deque)
    def check(self,key,limit,window=60):
        now=time.monotonic(); q=self.events[key]
        while q and q[0]<=now-window: q.popleft()
        if len(q)>=limit: return max(1,int(window-(now-q[0]))+1)
        q.append(now)
        if len(self.events)>5000:
            self.events={k:v for k,v in self.events.items() if v and v[-1]>now-window}
            self.events=defaultdict(deque,self.events)
        return 0
