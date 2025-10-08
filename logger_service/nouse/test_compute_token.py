from logger_service.token_calculator import compute_token_usage


def test_without_provider():
    messages = [
        {"role": "user", "content": "Hello, this is a test message."},
        {"role": "assistant", "content": "Hi, how can I help?"}
    ]
    res = compute_token_usage(None, messages, model_name="gpt-test", model_config={"input_cost_per_1k": 0.001, "output_cost_per_1k": 0.002}, response_text="This is a reply from the model.")
    print("Test without provider:", res)


def test_with_provider():
    # simulate provider response usage shape
    provider_resp = {"usage": {"prompt_tokens": 10, "completion_tokens": 6, "total_tokens": 16}}
    messages = [{"role": "user", "content": "Hello"}]
    res = compute_token_usage(provider_resp, messages, model_name="gpt-test", model_config={"input_cost_per_1k": 0.01, "output_cost_per_1k": 0.02})
    print("Test with provider usage:", res)


def test_streaming_chunks():
    messages = [{"role": "user", "content": "Please summarize the following:"}]
    chunks = ["This is chunk one. ", "This is chunk two, continuing the sentence.", " Final chunk."]
    # use library function to join and compute
    from logger_service.token_calculator import compute_token_usage_from_chunks, chunk_token_counts, aggregate_chunk_counts
    res = compute_token_usage_from_chunks(None, messages, model_name="gpt-test", model_config={"input_cost_per_1k": 0.001, "output_cost_per_1k": 0.002}, chunks=chunks)
    counts = chunk_token_counts(chunks, model_name="gpt-test")
    agg = aggregate_chunk_counts(counts)
    print("Streaming merged result:", res)
    print("Per-chunk counts:", counts)
    print("Aggregated chunk counts:", agg)


if __name__ == '__main__':
    test_without_provider()
    test_with_provider()
    test_streaming_chunks()
