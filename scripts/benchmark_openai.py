"""Run the OpenAI-only routing benchmark with actual accuracy and latency."""
import argparse
import asyncio
from evaluate import evaluate

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--limit',type=int,default=0)
    parser.add_argument('--concurrency',type=int,default=2)
    args=parser.parse_args()
    asyncio.run(evaluate(args.limit,args.concurrency,output='reports/benchmark-openai.json'))
