import asyncio
import random
import aiohttp
import time
from transformers import AutoTokenizer
import json
import numpy as np

def load_test_prompts_arxiv_math():
    arxiv_prompts = []
    file_path = "./arxiv-math-instruct.jsonl"
    with open(file_path, 'r') as file:
        for line in file:
            json_object = json.loads(line)
            question = json_object.get("question")
            answer = json_object.get("answer")
            arxiv_prompts.append((question, answer))
    return arxiv_prompts

def load_test_prompts_pure_dove():
    puredove_prompts = []
    file_path = "./pure-dove.jsonl"
    with open(file_path, 'r') as file:
        for line in file:
            json_object = json.loads(line)
            if "conversation" in json_object:
                conversation = json_object["conversation"]
                if len(conversation) > 0:
                    first_input = conversation[0]["input"]
                    first_output = conversation[0]["output"]
                    puredove_prompts.append((first_input, first_output))
    return puredove_prompts

def generate_request(prompt, output_token_count):
    """Generates request for given model server"""
    pload = {
        "prompt": prompt,
        #"n": 1,
        #"best_of": 1,
        "use_beam_search": False,
        "temperature": 0.0,
        #"top_p": 1.0,
        "max_tokens": output_token_count,
        "ignore_eos": False,
        "stream": False,
    }
    return pload

async def _send_chat_completion(session, prompt, resp, url, result_queue, prompt_type, max_retries=1):
    output_token_count = len(tokenizer.encode(resp))
    
    for attempt in range(max_retries):
        req_start_time = time.perf_counter()
        try:
            async with session.post(url=url,
                                    json=generate_request(prompt, output_token_count),
                                    headers={"Content-Type": "application/json"}) as response:
                response_json = await response.json()
                req_end_time = time.perf_counter()
                latency = req_end_time - req_start_time
                await result_queue.put((response_json, latency, req_start_time, req_end_time, prompt, prompt_type))
                return
        except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError, aiohttp.ClientOSError) as e:
            if attempt == max_retries - 1:
                req_end_time = time.perf_counter()
                latency = -1
                await result_queue.put((None, latency, req_start_time, req_end_time, prompt, prompt_type))
            else:
                wait_time = 2 ** attempt  # Exponential backoff
                await asyncio.sleep(wait_time)

async def producer(no_of_messages, rate_per_second, session, result_queue):
    global arxiv_prompt, pure_dove_prompt
    urls = ["http://34.143.183.39:80/generate", "http://35.240.213.14:80/generate"]
    
    for _ in range(no_of_messages):
        if random.uniform(0, 1) > 1:
            prompt_resp = random.choice(arxiv_prompt)
            url = urls[0]
            prompt_type = 'arxiv'
        else:
            prompt_resp = random.choice(pure_dove_prompt)
            url = urls[1]
            prompt_type = 'puredove'
        if random.uniform(0, 1) > 1:
            url = urls[0]
        else:
            url = urls[1]



        asyncio.create_task(_send_chat_completion(session, prompt_resp[0], prompt_resp[1], url, result_queue, prompt_type))
        await asyncio.sleep(1 / rate_per_second)  # Maintain the rate of requests per second

async def consumer(result_queue, no_of_messages):
    responses = []
    latencies = []
    req_start_times = []
    req_end_times = []
    prompts = []
    successful_requests = 0
    
    arxiv_latencies = []
    puredove_latencies = []
    arxiv_requests = 0
    puredove_requests = 0
    
    for _ in range(no_of_messages):
        result = await result_queue.get()
        if result[0] is not None:
            successful_requests += 1
            responses.append(result[0])
            latencies.append(result[1])
            if result[5] == 'arxiv':
                arxiv_latencies.append(result[1])
                arxiv_requests += 1
            elif result[5] == 'puredove':
                puredove_latencies.append(result[1])
                puredove_requests += 1
            req_start_times.append(result[2])
            req_end_times.append(result[3])
            prompts.append(result[4])
    
    return responses, latencies, req_start_times, req_end_times, prompts, successful_requests, arxiv_latencies, puredove_latencies, arxiv_requests, puredove_requests

async def _send_async_requests(no_of_messages, rate_per_second):
    result_queue = asyncio.Queue()
    timeout = aiohttp.ClientTimeout(total=6000)  # Set total timeout to 60 seconds
    
    connector = aiohttp.TCPConnector(limit_per_host=10000)  # Limit concurrent connections per host
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        start_time = time.perf_counter()  # Start time for the entire request batch
        producer_task = asyncio.create_task(producer(no_of_messages, rate_per_second, session, result_queue))
        consumer_task = asyncio.create_task(consumer(result_queue, no_of_messages))
        
        await producer_task
        results = await consumer_task
        responses, latencies, req_start_times, req_end_times, prompts, successful_requests, arxiv_latencies, puredove_latencies, arxiv_requests, puredove_requests = results
        end_time = time.perf_counter()  # End time for the entire request batch
    
    # Calculate average latencies for both prompt types
    avg_latency_arxiv = np.mean(arxiv_latencies) if arxiv_latencies else float('inf')
    avg_latency_puredove = np.mean(puredove_latencies) if puredove_latencies else float('inf')
    avg_latency_overall = np.mean(latencies) if latencies else float('inf')
    
    # Calculate total tokens sent and received
    total_tokens_sent = sum([len(tokenizer.encode(prompt)) for prompt in prompts])
    total_tokens_received = sum([len(tokenizer.encode(resp["text"][0])) for resp in responses if resp])
    
    # Calculate time duration
    time_duration = max(req_end_times) - min(req_start_times)
    time_duration_sent = max(req_start_times) - min(req_start_times)
    time_duration_received = max(req_end_times) - min(req_end_times)
    
    # Calculate tokens per second
    tokens_sent_per_sec = total_tokens_sent / time_duration_received if time_duration_received > 0 else 0
    tokens_received_per_sec = total_tokens_received / time_duration_received if time_duration_received > 0 else 0
    
    print(f'No of req sent: {no_of_messages}')
    print(f'No of req received: {len(responses)}')
    print(f'Total duration: {time_duration}')
    print(f'QPS: {no_of_messages / time_duration_sent if time_duration_sent > 0 else 0}')
    print(f'tokens sent per req: {total_tokens_sent / successful_requests if successful_requests > 0 else 0}')
    print(f'tokens rcvd per req: {total_tokens_received / successful_requests if successful_requests > 0 else 0}')
    print(f'Number of successful requests: {successful_requests}')
    
    print(f'Number of arxiv requests: {arxiv_requests}')
    print(f'Number of puredove requests: {puredove_requests}')
    
    print(f'Average latency for arxiv prompts: {avg_latency_arxiv:.4f} seconds')
    print(f'Average latency for puredove prompts: {avg_latency_puredove:.4f} seconds')
    print(f'Overall average latency: {avg_latency_overall:.4f} seconds')
    
    return avg_latency_arxiv, avg_latency_puredove, avg_latency_overall, tokens_sent_per_sec, tokens_received_per_sec


global tokenizer
global arxiv_prompt
global pure_dove_prompt

hf_tokenizer_model = "meta-llama/Llama-2-7b-chat-hf"
tokenizer = AutoTokenizer.from_pretrained(hf_tokenizer_model)

arxiv_prompt = load_test_prompts_arxiv_math()
pure_dove_prompt = load_test_prompts_pure_dove()
duratios  = 1000  # Number of messages to be sent in total
rate_per_second_list =[0.5, 5, 10, 15, 20, 25, 30, 35, 40]

for rate_per_second in reversed(rate_per_second_list):
    no_of_messages = 2500
    print(f'rate {rate_per_second}')
    avg_latency_arxiv, avg_latency_puredove, avg_latency_overall, tokens_sent_per_sec, tokens_received_per_sec = asyncio.run(_send_async_requests(no_of_messages, rate_per_second))
    print(f'Tokens Sent per Second: {tokens_sent_per_sec:.2f}')
    print(f'Tokens Received per Second: {tokens_received_per_sec:.2f}')
    time.sleep(10)
