import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3n from 'aws-cdk-lib/aws-s3-notifications';
import { aws_bedrock as bedrock } from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';

export class AIPOCStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    
    const manualKbId = '5UVPIX5IBN';
    const manualDsId = 'UD1NFIWNLD';

    // CREATE THE AGENT IAM ROLE
    const agentRole = new iam.Role(this, 'BedrockAgentsRole', {
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com'),
      inlinePolicies: {
        'BedrockAgentPolicy': new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              actions: ['bedrock:InvokeModel',
                'bedrock:InvokeModelWithResponseStream'
              ],
              resources: [
                `arn:aws:bedrock:${this.region}::foundation-model/*`,
                'arn:aws:bedrock:*::inference-profile/*',
                'arn:aws:bedrock:*::foundation-model/*',
                `arn:aws:bedrock:${this.region}:${this.account}:inference-profile/*`
              ],
            }),
            new iam.PolicyStatement({
              actions: ['bedrock:Retrieve'],
              resources: [
                `arn:aws:bedrock:${this.region}:${this.account}:knowledge-base/${manualKbId}`
              ],
            }),
          ],
        }),
      },
    });

    // POC Agent
    const agent1 = new bedrock.CfnAgent(this, 'PocAgent1', {
      agentName: 'poc-agent',
      agentResourceRoleArn: agentRole.roleArn,
      autoPrepare:true,
      foundationModel: 'us.anthropic.claude-haiku-4-5-20251001-v1:0',
      idleSessionTtlInSeconds: 600,
      instruction: `You are an Insurance Policy Coverage Checker AI.
Your task is to determine whether a user's requested treatment or prescription is covered under a specified health insurance policy.

Behaviour Instructions:

1. Always wait for the user to specify which policy to check.
    If the user does not specify a policy, return the following JSON:
     {
       "covered": false,
       "confidence": 0.0,
       "explanation": "No policy specified to check coverage against.",
       "evidence": []
     }
    Then prompt the user with:
    "Please specify which insurance policy you'd like me to check this request against."

2. Once a policy is provided:
    Carefully match the user's treatment/prescription request against the content of that specific policy.
    Use only the policy's actual language—do not infer, assume, or invent coverage details.

3. Response Format:
    Always reply using this strict JSON format:
     {
       "covered": true/false,
       "confidence": float (0.0 to 1.0),
       "explanation": "one short sentence explaining why",
       "evidence": ["exact policy snippet 1", "exact policy snippet 2"]
     }

4. Confidence Rules:
    Use high confidence (>= 0.8) only when the policy explicitly confirms or denies the requested service.
    Use low confidence (< 0.5) when:
      The policy does not mention the treatment.
      Coverage is ambiguous or implied but not directly stated.

5. Evidence Requirements:
    All evidence must be direct quotes from the policy.
    Do not paraphrase or summarize.
    If there is no direct mention, evidence should be an empty list ([]).

6. Rejection Rule:
    If the policy does not address the treatment, return:
     {
       "covered": false,
       "confidence": (a value < 0.5),
       "explanation": "The policy does not mention this treatment.",
       "evidence": []
     }`,
      knowledgeBases: [{
        knowledgeBaseId: manualKbId,
        description: 'internal: knowledgebase includes information about the insurance policies based on which you should be answering',
        knowledgeBaseState: 'ENABLED'
      }]
    });

    const agent1Alias = new bedrock.CfnAgentAlias(this, 'PocAgent1Alias', {
      agentAliasName: 'Version-1',
      agentId: agent1.attrAgentId,
    });

    // POC Agent-2
    const agent2 = new bedrock.CfnAgent(this, 'PocAgent2', {
      agentName: 'poc-agent-2',
      agentResourceRoleArn: agentRole.roleArn,
      autoPrepare:true,
      foundationModel: 'us.anthropic.claude-haiku-4-5-20251001-v1:0',
      idleSessionTtlInSeconds: 600,
      instruction: `You are an insurance policy reasoning assistant.

You will be given:
A health insurance policy (as text or extracted snippets).
A user prescription/treatment request.

Your task:
Determine whether the requested treatment/prescription is covered under the policy.
Provide a structured, but more verbose rationale with citations.

Return your answer ONLY in strict JSON format:
{
  "covered": true/false,
  "confidence": float between 0 and 1,
  "detailed_reasoning": "2-3 sentences explaining the reasoning behind the decision",
  "citations": [
    {"section": "Section/Subsection/Clause", "text": "policy snippet text"}
  ]
}

Guidelines:
Always ground your reasoning in directly quoted policy snippets.
If the policy text is ambiguous, explain why it is unclear and lower confidence (<0.5).
Unlike Agent 1, do not be overly brief — expand slightly to give the Judge more material.
Never make assumptions beyond the given policy.`,
      knowledgeBases: [{
        knowledgeBaseId: manualKbId,
        description: 'UNDEFINED',
        knowledgeBaseState: 'ENABLED'
      }]
    });

    const agent2Alias = new bedrock.CfnAgentAlias(this, 'PocAgent2Alias', {
      agentAliasName: 'Version-1',
      agentId: agent2.attrAgentId,
    });

    //DYNAMODB MAPPING TABLE
    const policyMappingTable = new dynamodb.Table(this, 'HealthiPocMappingTable', {
      partitionKey: { name: 'email', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,      
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // S3 Bucket
    const knowledgeBaseBucket = new s3.Bucket(this, 'KnowledgeBaseBucket', {
      bucketName: `knowledge-base-agent-${this.account}`, 
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      removalPolicy: cdk.RemovalPolicy.RETAIN, 
    });

    // Document Upload Function
    const docUploadFunction = new lambda.Function(this, 'DocUploadFunction', {
      functionName: 'doc-upload-function',
      runtime: lambda.Runtime.PYTHON_3_13,
      handler: 'lambda_function.lambda_handler',
      code: lambda.Code.fromAsset('src/doc-upload'), 
      memorySize: 128,
      timeout: cdk.Duration.seconds(120),
      
      environment: {
        KB_ID: manualKbId,
        KB_DS_ID: manualDsId,
      },
    });

    // Document Delete Function 
    const docDeleteFunction = new lambda.Function(this, 'DocDeleteFunction', {
      functionName: 'doc-delete-function',
      runtime: lambda.Runtime.PYTHON_3_13,
      handler: 'lambda_function.lambda_handler',
      code: lambda.Code.fromAsset('src/doc-delete'),
      memorySize: 128,
      timeout: cdk.Duration.seconds(120),

      environment: {
        KB_ID: manualKbId,
        KB_DS_ID: manualDsId,
      },
    });

    // LLM as a Judge Function 
    const psycopgLayer = lambda.LayerVersion.fromLayerVersionArn(
      this, 
      'PsycopgLayer', 
      'arn:aws:lambda:us-east-1:770693421928:layer:Klayers-p312-psycopg2-binary:1' 
    );

    const customPsycopgLayer = new lambda.LayerVersion(this, 'CustomPsycopgLayer', {
      layerVersionName: 'psycog-custom-layer',
      code: lambda.Code.fromAsset('src/layers/psycog-layer'),
      compatibleRuntimes: [
        lambda.Runtime.PYTHON_3_12,
        lambda.Runtime.PYTHON_3_13
      ],
      description: 'Custom psycog layer managed automatically by CDK',
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    const llmJudgeFunction = new lambda.Function(this, 'LlmAsAJudgeFunction', {
      functionName: 'llm-as-a-judge',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'lambda_function.lambda_handler',
      code: lambda.Code.fromAsset('src/llm-judge'),
      memorySize: 3008,
      timeout: cdk.Duration.seconds(180),
      layers: [psycopgLayer, customPsycopgLayer], 
      
      environment: {
        DB_NAME: 'query_responses',
        DB_PASS: '9KsEb2UwJ4KLFHQ9TcSV', 
        DB_HOST: 'healthi-agent-responses.c1gieku6q1gp.us-west-2.rds.amazonaws.com',
        DB_USER: 'postgres',
        KNOWLEDGE_BASE_ID: manualKbId,
        
        S3_BUCKET_NAME: knowledgeBaseBucket.bucketName,

        DDB_TABLE: policyMappingTable.tableName,
        AGENT1_ID: agent1.attrAgentId,
        AGENT1_ALIAS_ID: 'TSTALIASID',
        AGENT2_ID: agent2.attrAgentId,
        AGENT2_ALIAS_ID: 'TSTALIASID',
      },
    });
    policyMappingTable.grantReadWriteData(llmJudgeFunction);

    // Grant the LLM Judge Lambda permissions to access required AWS services
    llmJudgeFunction.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        
        'bedrock:InvokeAgent',
        'bedrock:InvokeModel',
        'bedrock:InvokeModelWithResponseStream',
        'bedrock:Retrieve',
        
    
        'textract:DetectDocumentText',
        'textract:GetDocumentTextDetection',
        
        
        's3:PutObject',
        's3:GetObject',
        
        
        'dynamodb:Query',
        'dynamodb:GetItem'
      ],
      resources: ['*'], 
    }));

    // API Gateway 
    const judgeIntegration = new HttpLambdaIntegration('JudgeIntegration', llmJudgeFunction);

    const httpApi = new apigwv2.HttpApi(this, 'JudgeHttpApi', {
      apiName: 'LLM Judge HTTP API',
      description: 'Fast, cost-effective HTTP API for the LLM Judge Lambda function',
    });

    httpApi.addRoutes({
      path: '/upload',
      methods: [apigwv2.HttpMethod.POST], 
      integration: judgeIntegration,
    });

    // S3 Event Notifications 
    knowledgeBaseBucket.addEventNotification(
      s3.EventType.OBJECT_CREATED,
      new s3n.LambdaDestination(docUploadFunction)
    );
    
    knowledgeBaseBucket.addEventNotification(
      s3.EventType.OBJECT_REMOVED,
      new s3n.LambdaDestination(docDeleteFunction)
    );
  }
}