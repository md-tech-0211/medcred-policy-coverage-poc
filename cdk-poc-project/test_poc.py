import boto3

bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
KB_ID = '5UVPIX5IBN' 

def run_edge_case_test(test_name, query, filter_value):
    print(f"\n{'='*60}")
    print(f"TEST: {test_name}")
    print(f"QUERY: '{query}'")
    print(f"FILTER: 'story_type' = '{filter_value}'")
    print(f"{'-'*60}")
    
    try:
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=KB_ID,
            retrievalQuery={'text': query},
            retrievalConfiguration={
                'vectorSearchConfiguration': {
                    'filter': {
                        'equals': {
                            'key': 'story_type',
                            'value': filter_value
                        }
                    }
                }
            }
        )
        
        results = response.get('retrievalResults', [])
        if not results:
            print("❌ RESULT: No text found. (The filter successfully blocked irrelevant data!)")
        else:
            print(f"RESULT: Found {len(results)} matching chunks.")
            for i, result in enumerate(results, 1):
                score = result.get('score', 0)
                text = result['content']['text'].replace('\n', ' ')
                print(f"   Snippet {i} [Relevance: {score:.2f}]: {text[:130]}...")
                
    except Exception as e:
        print(f"⚠️ API ERROR: {e}")

print("\n STARTING BEDROCK RAG TEST ...\n")

# ---------------------------------------------------------
# EDGE CASE 1: The Ambiguity Test
# Asking the exact same generic question, but relying on the filter to grab the right facts.
# ---------------------------------------------------------
run_edge_case_test(
    test_name="Ambiguity Test 1 (Zebra)",
    query="What is the name of the lion and where does he live?",
    filter_value="zebra_truce"
)

run_edge_case_test(
    test_name="Ambiguity Test 2 (Mouse)",
    query="What is the name of the lion and where does he live?",
    filter_value="mouse_rescue"
)

# ---------------------------------------------------------
# EDGE CASE 2: The Hallucination Trap (Cross-Context Query)
# Asking about the Mouse story, but forcing it to look ONLY in the Zebra story.
# (Proof that cross-policy bleeding is impossible).
# ---------------------------------------------------------
run_edge_case_test(
    test_name="The Hallucination Trap",
    query="Did a tiny mouse chew through a steel net to save the lion?",
    filter_value="zebra_truce"
)

# ---------------------------------------------------------
# EDGE CASE 3: The Missing Policy Test
# What happens if the UI sends a policy name that doesn't exist in the database?
# ---------------------------------------------------------
run_edge_case_test(
    test_name="Invalid Metadata / Missing Policy",
    query="How did the lion survive?",
    filter_value="invalid_fake_policy_name"
)

print(f"\n{'='*60}")
print("TEST COMPLETE")