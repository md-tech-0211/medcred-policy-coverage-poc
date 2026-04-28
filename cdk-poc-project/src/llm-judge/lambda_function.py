import base64
import boto3
import uuid
import json
import logging
import os
import psycopg2
from boto3.dynamodb.conditions import Key

s3 = boto3.client('s3')
textract = boto3.client('textract')
bedrock_agent = boto3.client('bedrock-agent-runtime')
bedrock_runtime = boto3.client('bedrock-runtime')
dynamodb = boto3.resource('dynamodb')

S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')
#BUCKET_NAME = 'medical-prescption-ocr'
ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.pdf']

# AGENT1_ID = 'PZ6VMOYKD5'
# # AGENT1_ALIAS_ID = 'JBJ7JACPG4'
# AGENT1_ALIAS_ID = 'TZIQDETHI6'


# AGENT2_ID = 'OG43YWOMLO'
# # AGENT2_ALIAS_ID = 'DQXAEOGW7R'
# AGENT2_ALIAS_ID = 'WKRWERDN8W'

AGENT1_ID = os.environ.get("AGENT1_ID")
AGENT1_ALIAS_ID = os.environ.get("AGENT1_ALIAS_ID")

AGENT2_ID = os.environ.get("AGENT2_ID")
AGENT2_ALIAS_ID = os.environ.get("AGENT2_ALIAS_ID")

JUDGE_MODEL_ID = 'us.anthropic.claude-sonnet-4-6'

# Knowledge Base Configuration
KNOWLEDGE_BASE_ID = os.environ.get("KNOWLEDGE_BASE_ID")  # Add your KB ID
DATA_SOURCE_ID = os.environ.get("DATA_SOURCE_ID")



logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DB
DB_HOST = os.environ["DB_HOST"]
DB_NAME = os.environ["DB_NAME"]
DB_USER = os.environ["DB_USER"]
DB_PASS = os.environ["DB_PASS"]
DB_PORT = os.environ.get("DB_PORT", 5432)
DDB_TABLE = os.environ.get("DDB_TABLE", "healthi-poc-tables")


# def retrieve_policy_context(query, policy_name, max_results=10):
#     """
#     Retrieve relevant policy context using metadata filtering.
#     This function uses Bedrock Knowledge Base with metadata filtering.
#     """
#     if not KNOWLEDGE_BASE_ID or not policy_name:
#         return None
    
#     try:
#         # Create metadata filter for the specific policy
#         # metadata_filter = {
#         #     "andAll": [
#         #         {
#         #             "equals": {
#         #                 "key": "policy_name",  # Assuming your documents have this metadata field
#         #                 "value": policy_name
#         #             }
#         #         }
#         #     ]
#         # }
#         conditions = [
#             {
#                 "equals": {
#                     "key": "policy_name",  # Documents should include this metadata field
#                     "value": policy_name
#                 }
#             }
#         ]

#         metadata_filter = conditions[0] if len(conditions) == 1 else {"andAll": conditions}
        
#         # You might also want to filter by document type
#         # metadata_filter["andAll"].append({
#         #     "equals": {
#         #         "key": "document_type",
#         #         "value": "policy_document"
#         #     }
#         # })
        
#         response = bedrock_agent.retrieve(
#             knowledgeBaseId=KNOWLEDGE_BASE_ID,
#             retrievalQuery={
#                 'text': query
#             },
#             retrievalConfiguration={
#                 'vectorSearchConfiguration': {
#                     'numberOfResults': max_results,
#                     'overrideSearchType': 'SEMANTIC',  # Use both semantic and keyword search
#                     'filter': metadata_filter
#                 }
#             }
#         )
        
#         logger.info(f"XXXXXXX Retrieved {len(response.get('retrievalResults', []))} ")
        
#         # Extract and combine relevant passages
#         relevant_passages = []
#         for result in response.get('retrievalResults', []):
#             content = result.get('content', {}).get('text', '')
#             score = result.get('score', 0)
#             metadata = result.get('metadata', {})
            
#             # Only include results with reasonable relevance scores
#             if score > 0.3:  # Adjust threshold as needed
#                 relevant_passages.append({
#                     'content': content,
#                     'score': score,
#                     'metadata': metadata
#                 })
        
#         if relevant_passages:
#             # Sort by relevance score
#             relevant_passages.sort(key=lambda x: x['score'], reverse=True)
            
#             # Combine the most relevant passages
#             combined_context = "\n\n".join([
#                 f"[Relevance: {passage['score']:.2f}] {passage['content']}" 
#                 for passage in relevant_passages[:5]  # Top 5 passages
#             ])
            
#             logger.info(f"Retrieved {len(relevant_passages)} relevant passages for policy: {policy_name}")
#             return combined_context
#         else:
#             logger.warning(f"No relevant policy context found for policy: {policy_name}")
#             return None
            
#     except Exception as e:
#         logger.error(f"Error retrieving policy context: {e}")
#         return None






def retrieve_policy_context(query, policy_name, max_results=10):
    """
    Retrieve relevant policy context from Bedrock KB restricted to documents where:
        policy_name == <policy_name>

    Notes:
    - Expects S3 sidecar metadata to include a 'policy_name' attribute using the
      typed 'metadataAttributes' schema.
    - Uses a single 'equals' filter (no andAll/orAll).
    - Post-filters defensively to prevent any cross-policy bleed.
    """
    if not KNOWLEDGE_BASE_ID or not policy_name:
        logger.warning("[KB] Missing KNOWLEDGE_BASE_ID or policy_name; skipping retrieval.")
        return None

    def _do_retrieve(filter_obj=None):
        cfg = {"numberOfResults": max_results}
        if filter_obj:
            cfg["filter"] = filter_obj
        return bedrock_agent.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={"text": query},
            retrievalConfiguration={"vectorSearchConfiguration": cfg},
        )

    def _get_by_path(d, path):
        cur = d
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        return cur

    def _deep_has_policy_name(md, expected):
        if isinstance(md, dict):
            for k, v in md.items():
                if k == "policy_name" and v == expected:
                    return True
                if isinstance(v, (dict, list)) and _deep_has_policy_name(v, expected):
                    return True
        elif isinstance(md, list):
            return any(_deep_has_policy_name(x, expected) for x in md)
        return False

    def _combine(filtered):
        filtered.sort(key=lambda x: x["score"], reverse=True)
        return "\n\n".join(
            f"[Relevance: {p['score']:.2f}] {p['content']}"
            for p in filtered[: min(5, len(filtered))]
        )

    # --- 1) Filter directly on the attribute name
    primary_filter = {"equals": {"key": "policy_name", "value": policy_name}}

    try:
        resp = _do_retrieve(primary_filter)
        raw = resp.get("retrievalResults", []) or []
        logger.info(f"[KB] Raw results with filter key 'policy_name': {len(raw)} for policy '{policy_name}'")

        # Hard post-filter: accept only chunks whose metadata shows policy_name == expected
        filtered = []
        for r in raw:
            md = r.get("metadata") or {}
            md_attrs = (
                md.get("metadataAttributes")
                or md.get("attributes")
                or {}
            )
            # Try common locations, then deep-scan as last resort
            value = md_attrs.get("policy_name")
            ok = (value == policy_name) or _deep_has_policy_name(md, policy_name)

            content = (r.get("content") or {}).get("text") or ""
            score = float(r.get("score") or 0.0)
            if ok and content and score > 0.4:
                filtered.append({"content": content, "score": score, "metadata": md})

        if filtered:
            logger.info(f"[KB] Returning {len(filtered)} passages after filter/post-filter for policy '{policy_name}'")
            return _combine(filtered)

        logger.warning(f"[KB] No matches via attribute filter; likely the doc wasn't ingested with 'policy_name' yet.")
        return None

    except Exception as e:
        logger.error(f"[KB] Error retrieving policy context: {e}")
        return None
        
def call_agent_with_policy_context(agent_id, alias_id, query, extracted_text, policy_name=None, policy_context=None):
    """Enhanced agent call that includes policy-specific context from Knowledge Base."""
    session_id = str(uuid.uuid4())
    
    # Build the agent input with policy context
    agent_input_parts = []
    
    # Add policy context if available
    # if policy_context:
    #     agent_input_parts.append(f"RELEVANT POLICY INFORMATION:\n{policy_context}")

    if policy_context:
        agent_input_parts.append(f"RELEVANT POLICY INFORMATION:\n{policy_context}")
    else:
        # >>> STRICT GUARDRAIL
        agent_input_parts.append(
            "IMPORTANT SYSTEM INSTRUCTION:\n"
            "No policy KB context matched the user's policy. You MUST NOT answer using generic knowledge, "
            "other policies, or web search. Respond ONLY with:\n"
            "\"I couldn't find policy documents for the requested policy in our knowledge base, so I can’t answer. "
            "Please re-upload or re-sync the policy materials.\"\n"
            "Do not add any other content."
        )


    # Add OCR extracted text if available
    if extracted_text:
        agent_input_parts.append(f"MEDICAL DOCUMENT CONTENTS:\n{extracted_text}")
    
    # Add policy name
    if policy_name:
        agent_input_parts.append(f"POLICY NAME: {policy_name}")
    
    # Add the user query
    agent_input_parts.append(f"USER QUESTION: {query}")
    
    # If no document was provided, add a note
    if not extracted_text:
        agent_input_parts.append("NOTE: No medical document was provided for analysis.")
    

    agent_input = "\n\n".join(agent_input_parts)


    # --- Debug logs ---
    logger.info(f"[AgentInput] length={len(agent_input)}")
    logger.info(f"[AgentInput] preview:\n{agent_input}")

    response = bedrock_agent.invoke_agent(
        agentId=agent_id,
        agentAliasId=alias_id,
        sessionId=session_id,
        inputText=query,
        sessionState={
            "promptSessionAttributes": {
                "policy_context": policy_context or "",
                "extracted_text": extracted_text or "",
                "policy_name": policy_name or ""
            }
        }
    )
    logger.info(f"Agent {agent_id} response: {response}")

    # full_response = ""
    # for event_stream in response['completion']:
    #     chunk = event_stream['chunk']['bytes'].decode('utf-8')
    #     logger.info(f"Chunk received: {chunk}")
    #     full_response += chunk

    full_response = ""

    for event in response['completion']:

        if 'chunk' in event:
            chunk = event['chunk']['bytes'].decode('utf-8')
            logger.info(f"Chunk received: {chunk}")
            full_response += chunk

        elif 'trace' in event:
            logger.info(f"Trace event: {event['trace']}")

        elif 'error' in event:
            logger.error(f"Agent error: {event['error']}")
            raise Exception(event['error'])

        else:
            logger.info(f"Other event: {event}")
    
    logger.info(f"Agent {agent_id} Full response: {full_response.strip()}")
    return full_response.strip()


def validate_ocr_with_llm(extracted_text, file_name, file_content):
    """Use LLM to validate and clean OCR extracted text."""
    validation_prompt = f"""
You are an OCR validation specialist. I have extracted text from a medical document using OCR, and I need you to validate and clean it.

Original OCR Extracted Text:
{extracted_text}

File Information:
- File: {file_name}

Please:
1. Review the extracted text for accuracy
2. Fix any obvious OCR errors (misspellings, garbled text, etc.)
3. Clean up formatting issues
4. Ensure medical terms are correctly spelled
5. Remove any artifacts or noise from OCR
6. Maintain the original structure and meaning

Respond with ONLY the cleaned and validated text. Do not add explanations or comments.
"""

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4000,
        "temperature": 0.1,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": validation_prompt}
                ]
            }
        ]
    }

    response = bedrock_runtime.invoke_model(
        modelId=JUDGE_MODEL_ID,
        body=json.dumps(body)
    )
    logger.info(f"Judge {response}")

    result = json.loads(response["body"].read())
    return result["content"][0]["text"].strip()


# def call_judge(query, agent1_response, agent2_response):
#     """Call Bedrock LLM directly as a judge."""
#     judge_prompt = f"""
# You are a judge model. Two insurance policy agents answered the same question.

# User Query:
# {query}

# Agent 1 Response:
# {agent1_response}

# Agent 2 Response:
# {agent2_response}

# Task:
# - Compare both answers.
# - Decide which is better supported and clearer.
# - Respond in strict JSON:

# {{
#   "winner": "agent1" or "agent2",
#   "reason": "short explanation why"
# }}
# """

#     body = {
#         "anthropic_version": "bedrock-2023-05-31",
#         "max_tokens": 500,
#         "temperature": 0.2,
#         "messages": [
#             {
#                 "role": "user",
#                 "content": [
#                     {"type": "text", "text": judge_prompt}
#                 ]
#             }
#         ]
#     }

#     response = bedrock_runtime.invoke_model(
#         modelId=JUDGE_MODEL_ID,
#         body=json.dumps(body)
#     )

#     result = json.loads(response["body"].read())
#     return result["content"][0]["text"].strip()




def call_judge(query, agent1_response, agent2_response):
    """
    Judge whether Agent 1 and Agent 2 provide the same substantive answer
    and how fully the (agreed) answer addresses the user's query.

    Returns a dict:
      {
        "status": "Covered" | "Partially Covered" | "Not Covered" | "Unsure",
        "confidence": float (0..1),
        "rationale": str  # short explanation (<= ~60 words)
      }
    """
    judge_prompt = f"""
You are evaluating two insurance policy answers to the same user query.

User Query:
{query}

Agent 1 Response:
{agent1_response}

Agent 2 Response:
{agent2_response}

Your tasks:
1) Determine the final insurance coverage status based on the agents' findings.
2) Determine how fully the (agreed) answer addresses the user's query.

Output REQUIREMENTS:
- Respond with **ONLY** valid JSON (no preamble, no code fences).
- Use this schema exactly:
{{
  "status": "Covered" | "Partially Covered" | "Not Covered" | "Unsure",
  "confidence": number,  // 0..1
  "rationale": string    // concise, <= 60 words, no new facts
}}

STRICT STATUS GUIDELINES:
- "Not Covered": If EITHER agent correctly identifies that the treatment is an EXCLUSION or explicitly not covered in the policy, the final status MUST be "Not Covered".
- "Covered": Both agents agree the treatment is covered and cite supporting policy text.
- "Partially Covered": The responses agree on some parts, but coverage is limited (e.g., sub-limits apply). Do NOT use this for full exclusions.
- "Unsure": Insufficient detail in the policy to make a determination, or the agents completely contradict each other without citing clear exclusions.

Confidence heuristic:
- High confidence (0.8 - 1.0) if an explicit exclusion is found by either agent.
- High confidence if both agents agree and cite clear evidence.
- Decrease for ambiguity or missing key elements.
"""

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 600,
        "temperature": 0.2,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": judge_prompt}
                ]
            }
        ]
    }

    try:
        response = bedrock_runtime.invoke_model(
            modelId=JUDGE_MODEL_ID,
            body=json.dumps(body)
        )
        result = json.loads(response["body"].read())
        raw = (result.get("content") or [{}])[0].get("text", "").strip()
        
        raw = raw.replace('```json', '')
        raw = raw.replace('```', '').strip()

        # Parse and validate JSON
        parsed = json.loads(raw)
        status = parsed.get("status")
        confidence = parsed.get("confidence")
        rationale = parsed.get("rationale", "")

        valid_statuses = {"Covered", "Partially Covered", "Not Covered", "Unsure"}
        if status not in valid_statuses:
            raise ValueError("Invalid or missing 'status' field from judge.")
        if not isinstance(confidence, (int, float)):
            raise ValueError("Invalid or missing 'confidence' field from judge.")

        # Clamp and tidy
        confidence = max(0.0, min(1.0, float(confidence)))
        rationale = (rationale or "").strip()[:400]

        return {"status": status, "confidence": confidence, "rationale": rationale}

    except Exception as e:
        logger.error(f"Error calling judge: {e}")
        # Conservative fallback
        return {
            "status": "Unsure",
            "confidence": 0.0,
            "rationale": "Judge failed; unable to determine agreement or coverage."
        }


def process_multiple_files(parts, boundary):
    """Process multiple files from multipart form data."""
    import re
    import time
    import uuid # ensure uuid is available
    files = []
    policy_file = None # NEW: variable to hold the master policy
    query = "No query found"
    email = None
    policy_name = None
    
    for part in parts:
        if b'Content-Disposition' in part:
            header_text = part.split(b'\r\n\r\n', 1)[0].decode()
            
            # 1. Handle Medical Files
            if 'name="files[]"' in header_text or 'name="file"' in header_text or 'name="files"' in header_text:
                match = re.search(r'filename="(.+?)"', header_text)
                if match:
                    original_filename = match.group(1)
                    ext = original_filename.lower().split('.')[-1]
                    if f".{ext}" in ALLOWED_EXTENSIONS:
                        file_name = f"uploads/{uuid.uuid4()}.{ext}"
                        _, file_body = part.split(b'\r\n\r\n', 1)
                        if file_body.endswith(b'\r\n'):
                            file_body = file_body[:-2]
                        
                        files.append({
                            'filename': file_name,
                            'original_name': original_filename,
                            'content': file_body,
                            'extension': ext
                        })
                    else:
                        logger.warning(f"Unsupported file type: .{ext} for file {original_filename}")

            # 2. NEW: Handle the Master Policy PDF
            elif 'name="policy_file"' in header_text:
                match = re.search(r'filename="(.+?)"', header_text)
                if match:
                    original_filename = match.group(1)
                    ext = original_filename.lower().split('.')[-1]
                    # Save it in a different prefix 'policies/' to keep S3 clean
                    file_name = f"policies/{uuid.uuid4()}.{ext}" 
                    _, file_body = part.split(b'\r\n\r\n', 1)
                    if file_body.endswith(b'\r\n'):
                        file_body = file_body[:-2]
                    
                    policy_file = {
                        'filename': file_name,
                        'original_name': original_filename,
                        'content': file_body,
                        'extension': ext
                    }
            
            # 3. Handle Text Fields
            elif 'name="query"' in header_text:
                query = part.split(b'\r\n\r\n', 1)[-1].rsplit(b'\r\n')[0].decode("utf-8").strip()
            elif 'name="email"' in header_text:
                email = part.split(b'\r\n\r\n', 1)[-1].rsplit(b'\r\n')[0].decode("utf-8").strip()
            elif 'name="policy_name"' in header_text:
                policy_name = part.split(b'\r\n\r\n', 1)[-1].rsplit(b'\r\n')[0].decode("utf-8").strip() 
    
    # NEW: Return policy_file along with everything else
    return files, query, email, policy_name, policy_file


def process_multiple_documents_with_textract(files):
    """Process multiple documents using Textract."""
    all_extracted_texts = []
    all_cleaned_texts = []
    file_metadata = []
    
    for i, file_info in enumerate(files):
        try:
            # Upload file to S3
            s3.put_object(
                Bucket=S3_BUCKET_NAME, 
                Key=file_info['filename'], 
                Body=file_info['content']
            )
            
            # Run Textract on each file
            logger.info(f"Processing file {i+1}/{len(files)}: {file_info['original_name']}")
            textract_response = textract.detect_document_text(
                Document={'S3Object': {'Bucket': S3_BUCKET_NAME, 'Name': file_info['filename']}}
            )
            
            # Extract text from this document
            extracted_text = "\n".join(
                block["Text"] for block in textract_response["Blocks"] 
                if block["BlockType"] == "LINE"
            )
            
            # Clean and validate OCR text
            cleaned_text = validate_ocr_with_llm(
                extracted_text, 
                file_info['filename'], 
                file_info['content']
            )
            
            all_extracted_texts.append(extracted_text)
            all_cleaned_texts.append(cleaned_text)
            file_metadata.append({
                'filename': file_info['filename'],
                'original_name': file_info['original_name'],
                'extension': file_info['extension'],
                'status': 'success'
            })
            
            logger.info(f"Processed file {i+1}: {len(extracted_text)} chars extracted, {len(cleaned_text)} chars cleaned")
            
        except Exception as e:
            logger.error(f"Error processing file {file_info['original_name']}: {e}")
            # Continue with other files even if one fails
            all_extracted_texts.append("")
            all_cleaned_texts.append("")
            file_metadata.append({
                'filename': file_info['filename'],
                'original_name': file_info['original_name'],
                'extension': file_info['extension'],
                'status': 'error',
                'error': str(e)
            })
    
    return all_extracted_texts, all_cleaned_texts, file_metadata


def combine_multiple_documents(cleaned_texts, file_metadata):
    """Combine multiple documents into a single context."""
    combined_text = ""
    
    for i, (cleaned_text, metadata) in enumerate(zip(cleaned_texts, file_metadata)):
        if cleaned_text and metadata.get('status') == 'success':
            combined_text += f"\n\n--- Document {i+1}: {metadata['original_name']} ---\n"
            combined_text += cleaned_text
        elif metadata.get('status') == 'error':
            combined_text += f"\n\n--- Document {i+1}: {metadata['original_name']} (ERROR: {metadata.get('error', 'Unknown error')}) ---\n"
    
    return combined_text.strip()


def lambda_handler(event, context):
    import re
    import time
    import base64
    import json
    
    try:
        # ---- Parse Multipart Upload ----
        content_type = event['headers'].get('content-type') or event['headers'].get('Content-Type')
        body = event['body']
        if event.get('isBase64Encoded'):
            body = base64.b64decode(body)

        boundary = content_type.split("boundary=")[-1]
        parts = body.split(bytes(f"--{boundary}", "utf-8"))

        # 1. Process multiple files and unpack all 5 variables
        files, query, email, form_policy_name, policy_file = process_multiple_files(parts, boundary)
        logger.info(f"Received event with {len(files)} medical files, query: {query}")

        # Validate that we have at least a query
        if not query or query == "No query found":
            logger.error("No query found in the request.")
            return {"statusCode": 400, "body": "Query is required."}
        
        # Validate that we have at least one medical file
        if not files:
            logger.error("No medical files provided in the request.")
            return {"statusCode": 400, "body": "At least one medical file is required."}
        
        policy_name = form_policy_name

        # 2. FLOW 1 & 2: DYNAMODB AUTO-LEARNING & LOOKUP
        if email and DDB_TABLE:
            try:
                table = dynamodb.Table(DDB_TABLE)
                if policy_name:
                    # FLOW 1 (New User): Save the new mapping to DynamoDB automatically
                    logger.info(f"Saving new mapping to DynamoDB: {email} -> {policy_name}")
                    table.put_item(Item={'email': email, 'policy_name': policy_name})
                else:
                    # FLOW 2 (Returning User): Lookup the mapping if policy_name wasn't typed in
                    ddb_resp = table.query(KeyConditionExpression=Key("email").eq(email))
                    items = ddb_resp.get("Items", [])
                    if items:
                        policy_name = items[0].get('policy_name') or items[0].get('policyName')
                        logger.info(f"Auto-fetched policy from DB: {policy_name}")
            except Exception as e:
                logger.warning(f"DynamoDB operation failed: {e}")

        # Create or get user and session
        user_id = None
        session_id = None
        if email:
            user_id = get_or_create_user(email, policy_name)
            session_id = create_user_session(user_id)
            logger.info(f"Created session {session_id} for user {user_id}")

        # 3. FLOW 1: UPLOAD NEW MASTER POLICY & POLL SYNC
        if policy_file and policy_name and KNOWLEDGE_BASE_ID and DATA_SOURCE_ID:
            logger.info("New master policy document detected. Uploading and syncing...")
            
            bedrock_client = boto3.client('bedrock-agent')
            
            # A. Upload Policy PDF to S3
            s3.put_object(
                Bucket=S3_BUCKET_NAME, 
                Key=policy_file['filename'], 
                Body=policy_file['content']
            )
            
            # B. Upload Metadata JSON right next to it
            metadata = {
                "metadataAttributes": {
                    "policy_name": {
                        "value": {"type": "STRING", "stringValue": policy_name}, 
                        "includeForEmbedding": False
                    }
                }
            }
            s3.put_object(
                Bucket=S3_BUCKET_NAME, 
                Key=f"{policy_file['filename']}.metadata.json", 
                Body=json.dumps(metadata)
            )
            
            # C. Trigger & Poll the Ingestion Job (Race Condition Fix)
            try:
                job_resp = bedrock_client.start_ingestion_job(
                    knowledgeBaseId=KNOWLEDGE_BASE_ID, 
                    dataSourceId=DATA_SOURCE_ID
                )
                job_id = job_resp['ingestionJob']['ingestionJobId']
                logger.info(f"Started Bedrock ingestion job: {job_id}")
                
                # Poll for up to 15 seconds so Bedrock is ready BEFORE agents query it
                for _ in range(15):
                    status_resp = bedrock_client.get_ingestion_job(
                        knowledgeBaseId=KNOWLEDGE_BASE_ID, 
                        dataSourceId=DATA_SOURCE_ID, 
                        ingestionJobId=job_id
                    )
                    status = status_resp['ingestionJob']['status']
                    if status in ['COMPLETE', 'FAILED']:
                        logger.info(f"Sync finished with status: {status}")
                        break
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Failed to sync Knowledge Base: {e}")

        # 4. Process multiple medical documents
        extracted_texts, cleaned_texts, file_metadata = process_multiple_documents_with_textract(files)
        
        # Combine all documents into single context
        combined_text = combine_multiple_documents(cleaned_texts, file_metadata)
        logger.info(f"Combined text length: {len(combined_text)} characters")

        # 5. Retrieve policy-specific context from Knowledge Base
        policy_context = None
        if policy_name and KNOWLEDGE_BASE_ID:
            logger.info(f"Retrieving policy context for: {policy_name}")
            policy_context = retrieve_policy_context(query, policy_name)
            if policy_context:
                logger.info(f"Retrieved policy context: {policy_context[:200]}...")

        # Create request record with multiple files
        request_id = None
        file_metadata_json = None
        if session_id:
            file_names = [f['filename'] for f in file_metadata]
            raw_texts = " | ".join(extracted_texts)
            cleaned_texts_combined = " | ".join(cleaned_texts)
            
            request_id = create_user_request(
                session_id, query, 
                file_names[0] if file_names else None, 
                raw_texts, cleaned_texts_combined, 
                policy_name, policy_context
            )
            logger.info(f"Created request {request_id}")
            
            # Store file metadata as JSON in policy_context field
            file_metadata_json = store_file_metadata_in_json(request_id, file_metadata, extracted_texts, cleaned_texts)

        # ---- Call both Agents with Combined Document Context ----
        logger.info("Calling agents with combined document context...")
        agent1_response = call_agent_with_policy_context(
            AGENT1_ID, AGENT1_ALIAS_ID, query, combined_text, policy_name, policy_context
        )
        
        agent2_response = call_agent_with_policy_context(
            AGENT2_ID, AGENT2_ALIAS_ID, query, combined_text, policy_name, policy_context
        )

        # Store agent responses
        agent1_response_id = None
        agent2_response_id = None
        if request_id:
            agent1_response_id = insert_agent_response(request_id, "agent1", agent1_response)
            agent2_response_id = insert_agent_response(request_id, "agent2", agent2_response)

        # ---- Call Judge ----
        judge_response = call_judge(query, agent1_response, agent2_response)
        
        # Store judge response
        judge_id = None
        if request_id and agent1_response_id and agent2_response_id:
            judge_id = insert_judge_response(request_id, agent1_response_id, agent2_response_id, judge_response)

        return {
            'statusCode': 200,
            'body': json.dumps({
                'files_processed': len(files),
                'file_metadata': file_metadata,
                'email': email,
                'policy_name': policy_name,
                'policy_context_retrieved': bool(policy_context),
                'combined_ocr_text': combined_text,
                'individual_extracted_texts': extracted_texts,
                'individual_cleaned_texts': cleaned_texts,
                'agent1_response': agent1_response,
                'agent2_response': agent2_response,
                'judge': judge_response,
                'database_ids': {
                    'user_id': user_id,
                    'session_id': session_id,
                    'request_id': request_id,
                    'agent1_response_id': agent1_response_id,
                    'agent2_response_id': agent2_response_id,
                    'judge_id': judge_id
                },
                'file_metadata_json': file_metadata_json
            }),
            'headers': {'Content-Type': 'application/json'}
        }

    except Exception as e:
        logger.error(f"Error processing request: {e}")
        return {"statusCode": 500, "body": json.dumps({'error': str(e)})}


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=DB_PORT
    )


def get_or_create_user(email, policy_name=None):
    """Get existing user or create new one."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    result = cur.fetchone()
    
    if result:
        user_id = result[0]
        if policy_name:
            cur.execute(
                "UPDATE users SET policy_name = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (policy_name, user_id)
            )
    else:
        cur.execute(
            "INSERT INTO users (email, policy_name) VALUES (%s, %s) RETURNING id",
            (email, policy_name)
        )
        user_id = cur.fetchone()[0]
    
    conn.commit()
    cur.close()
    conn.close()
    return user_id


def create_user_session(user_id):
    """Create a new session for the user."""
    conn = get_db_connection()
    cur = conn.cursor()
    session_uuid = str(uuid.uuid4())
    
    cur.execute(
        "INSERT INTO user_sessions (user_id, session_uuid) VALUES (%s, %s) RETURNING id",
        (user_id, session_uuid)
    )
    session_id = cur.fetchone()[0]
    
    conn.commit()
    cur.close()
    conn.close()
    return session_id


def create_user_request(session_id, query, file_name=None, raw_ocr_text=None, cleaned_ocr_text=None, policy_name=None, policy_context=None):
    """Create a new request record with policy context."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        INSERT INTO user_requests (session_id, query, file_name, raw_ocr_text, cleaned_ocr_text, policy_name, policy_context)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
        """,
        (session_id, query, file_name, raw_ocr_text, cleaned_ocr_text, policy_name, policy_context)
    )
    request_id = cur.fetchone()[0]
    
    conn.commit()
    cur.close()
    conn.close()
    return request_id


def store_file_metadata_in_json(request_id, file_metadata, extracted_texts, cleaned_texts):
    """Store file metadata as JSON in the existing schema."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Create a JSON structure with file metadata
    file_metadata_json = {
        'files': [],
        'processing_summary': {
            'total_files': len(file_metadata),
            'successful_files': len([f for f in file_metadata if f.get('status') == 'success']),
            'failed_files': len([f for f in file_metadata if f.get('status') == 'error'])
        }
    }
    
    for i, (metadata, raw_text, cleaned_text) in enumerate(zip(file_metadata, extracted_texts, cleaned_texts)):
        file_info = {
            'file_index': i + 1,
            'filename': metadata['filename'],
            'original_name': metadata['original_name'],
            'extension': metadata['extension'],
            'status': metadata.get('status', 'completed'),
            'text_length': len(cleaned_text) if cleaned_text else 0,
            'error': metadata.get('error') if metadata.get('status') == 'error' else None
        }
        file_metadata_json['files'].append(file_info)
    
    # Update the user_requests table with file metadata
    cur.execute(
        """
        UPDATE user_requests 
        SET policy_context = COALESCE(policy_context, '') || 'FILE_METADATA:' || %s || '\n'
        WHERE id = %s;
        """,
        (json.dumps(file_metadata_json), request_id)
    )
    
    conn.commit()
    cur.close()
    conn.close()
    
    return file_metadata_json


def extract_file_metadata_from_policy_context(policy_context):
    """Extract file metadata JSON from policy_context field."""
    if not policy_context:
        return None
    
    try:
        # Look for FILE_METADATA: prefix in policy_context
        lines = policy_context.split('\n')
        for line in lines:
            if line.startswith('FILE_METADATA:'):
                json_str = line.replace('FILE_METADATA:', '')
                return json.loads(json_str)
    except (json.JSONDecodeError, AttributeError) as e:
        logger.warning(f"Failed to extract file metadata from policy_context: {e}")
    
    return None


def insert_agent_response(request_id, agent_type, response):
    """Insert agent response."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(
        "INSERT INTO agent_responses (request_id, agent_type, response) VALUES (%s, %s, %s) RETURNING id",
        (request_id, agent_type, response)
    )
    response_id = cur.fetchone()[0]
    
    conn.commit()
    cur.close()
    conn.close()
    return response_id


def insert_judge_response(request_id, agent1_response_id, agent2_response_id, judge_output):
    """Insert judge response."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        INSERT INTO judge_responses (request_id, agent1_response_id, agent2_response_id, judge_output)
        VALUES (%s, %s, %s, %s)
        RETURNING id;
        """,
        (request_id, agent1_response_id, agent2_response_id, json.dumps(judge_output))
    )
    judge_id = cur.fetchone()[0]
    
    conn.commit()
    cur.close()
    conn.close()
    return judge_id