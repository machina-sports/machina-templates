# Setup Guide - Alexa Sports Narrator

Complete setup guide for deploying the Alexa Sports Narrator skill.

## Prerequisites

### 1. Required Accounts

- **Amazon Developer Account**: https://developer.amazon.com
- **AWS Account**: For Lambda deployment
- **Machina Account**: For workflow execution

### 2. Required API Keys

- **Sportradar NFL API**: https://developer.sportradar.com
- **Sportradar NBA API**: https://developer.sportradar.com
- **Sportradar Soccer API**: https://developer.sportradar.com (optional)
- **OpenAI API**: https://platform.openai.com (or Google GenAI)

## Step-by-Step Setup

### Step 1: Create Alexa Skill

1. Go to [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask)
2. Click **Create Skill**
3. Enter skill information:
   - **Skill name**: Sports Narrator (or your custom name)
   - **Default language**: English (US)
   - **Choose a model to add to your skill**: Custom
   - **Choose a method to host your skill's backend**: Provision your own
4. Click **Create skill**
5. Choose **Start from Scratch** template
6. Click **Choose**

### Step 2: Configure Interaction Model

1. In the left sidebar, go to **Interaction Model** > **JSON Editor**
2. Copy the contents from `alexa-model/en-US.json`
3. Paste into the JSON Editor
4. Click **Save Model**
5. Click **Build Model** (this may take 1-2 minutes)

### Step 3: Add Additional Languages (Optional)

To add Portuguese support:

1. In the top right, click the language dropdown
2. Click **Language Settings**
3. Add **Portuguese (BR)**
4. Go to **Interaction Model** > **JSON Editor** for pt-BR
5. Copy contents from `alexa-model/pt-BR.json`
6. Save and build model

### Step 4: Deploy Lambda Function

#### Option A: AWS Console Deployment

1. **Prepare deployment package**:
   ```bash
   cd lambda/
   pip install -r requirements.txt -t ./package
   cd package
   zip -r ../deployment.zip .
   cd ..
   zip -g deployment.zip lambda_function.py
   ```

2. **Create Lambda function**:
   - Go to [AWS Lambda Console](https://console.aws.amazon.com/lambda)
   - Click **Create function**
   - Choose **Author from scratch**
   - Function name: `alexa-sports-narrator`
   - Runtime: **Python 3.11**
   - Architecture: **x86_64**
   - Click **Create function**

3. **Upload code**:
   - In **Code source** section, click **Upload from** > **.zip file**
   - Upload the `deployment.zip` file
   - Click **Save**

4. **Configure environment variables**:
   - Go to **Configuration** > **Environment variables**
   - Add:
     - `MACHINA_API_KEY`: your Machina API key
     - `MACHINA_BASE_URL`: https://api.machina.sports

5. **Increase timeout**:
   - Go to **Configuration** > **General configuration**
   - Edit timeout to **30 seconds** (Alexa requires response within 8s, but workflows may need more time)
   - Edit memory to **512 MB** (recommended)

6. **Add Alexa trigger**:
   - Go to **Configuration** > **Triggers**
   - Click **Add trigger**
   - Select **Alexa Skills Kit**
   - Enter your **Skill ID** (found in Alexa Developer Console)
   - Click **Add**

#### Option B: AWS CLI Deployment

```bash
# Set variables
FUNCTION_NAME="alexa-sports-narrator"
REGION="us-east-1"
ROLE_ARN="arn:aws:iam::YOUR_ACCOUNT_ID:role/lambda-execution-role"

# Create deployment package
cd lambda/
pip install -r requirements.txt -t ./package
cd package
zip -r ../deployment.zip .
cd ..
zip -g deployment.zip lambda_function.py

# Create function
aws lambda create-function \
  --function-name $FUNCTION_NAME \
  --runtime python3.11 \
  --role $ROLE_ARN \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://deployment.zip \
  --timeout 30 \
  --memory-size 512 \
  --region $REGION \
  --environment Variables="{MACHINA_API_KEY=your_key,MACHINA_BASE_URL=https://api.machina.sports}"

# Add Alexa permission
aws lambda add-permission \
  --function-name $FUNCTION_NAME \
  --statement-id alexa-skills-kit-invoke \
  --action lambda:InvokeFunction \
  --principal alexa-appkit.amazon.com \
  --event-source-token YOUR_SKILL_ID \
  --region $REGION
```

### Step 5: Link Lambda to Alexa Skill

1. In Alexa Developer Console, go to **Endpoint**
2. Select **AWS Lambda ARN**
3. Paste your Lambda ARN:
   ```
   arn:aws:lambda:us-east-1:123456789012:function:alexa-sports-narrator
   ```
4. Click **Save Endpoints**

### Step 6: Configure Machina Workflows

1. **Install workflows**:
   ```bash
   cd /path/to/machina-templates
   machina install skills/alexa-sports-narrator
   ```

2. **Configure secrets**:
   ```bash
   machina secret set SPORTRADAR_NFL_API_KEY "your_nfl_api_key"
   machina secret set SPORTRADAR_NBA_API_KEY "your_nba_api_key"
   machina secret set SPORTRADAR_SOCCER_API_KEY "your_soccer_api_key"
   machina secret set SDK_OPENAI_API_KEY "your_openai_api_key"
   ```

### Step 7: Test the Skill

#### In Alexa Simulator

1. Go to **Test** tab in Alexa Developer Console
2. Enable testing: **Test is enabled for this skill**
3. Try utterances:
   - "open sports narrator"
   - "what were the NFL scores today"
   - "how are the Lakers doing"

#### On Physical Device

1. Make sure you're logged into the same Amazon account
2. Say: "Alexa, open sports narrator"
3. Try various commands

#### View Logs

**Lambda Logs (CloudWatch)**:
```bash
aws logs tail /aws/lambda/alexa-sports-narrator --follow
```

**Machina Logs**:
```bash
machina logs workflow alexa-sports-query
```

## Certification & Publishing

### Before Submitting

1. **Test thoroughly**:
   - All intents work
   - Error handling is graceful
   - Responses are appropriate length
   - Multi-language works (if applicable)

2. **Privacy Policy**:
   - Create privacy policy if collecting user data
   - Host on public URL
   - Link in skill settings

3. **Icon & Description**:
   - Create 108x108px and 512x512px icons
   - Write compelling description
   - Add example phrases

### Submit for Certification

1. In Alexa Developer Console, go to **Distribution**
2. Fill in all required fields:
   - Public Name
   - One Sentence Description
   - Detailed Description
   - Example Phrases (3 required)
   - Icons (small & large)
   - Category: Sports
   - Keywords
   - Privacy Policy URL (if needed)

3. Go to **Privacy & Compliance**:
   - Answer all questions
   - Certify your skill

4. Go to **Availability**:
   - Select countries/regions
   - Set distribution date

5. Click **Submit for Review**

### Common Rejection Reasons

- Response too long (>90 seconds speech)
- Crashes or errors during testing
- Poor example phrases
- Missing privacy policy (if collecting data)
- Invocation name too generic

## Troubleshooting

### Lambda Times Out

- Increase Lambda memory (more memory = more CPU)
- Optimize workflow (reduce API calls)
- Add caching for frequent queries

### Skill Doesn't Respond

- Check Lambda CloudWatch logs
- Verify Alexa trigger is configured
- Test Lambda directly with sample event

### Wrong Data Returned

- Check Machina workflow outputs
- Verify API keys are correct
- Test workflow independently

### "The skill didn't respond properly"

- Lambda must respond within 8 seconds
- Check for exceptions in code
- Add try/catch blocks

## Maintenance

### Update Lambda Code

```bash
# Make changes to lambda_function.py
cd lambda/
zip -g deployment.zip lambda_function.py

aws lambda update-function-code \
  --function-name alexa-sports-narrator \
  --zip-file fileb://deployment.zip
```

### Update Interaction Model

1. Edit `alexa-model/en-US.json`
2. Paste into Alexa Developer Console JSON Editor
3. Save and rebuild model

### Update Workflows

```bash
# Edit workflow files
cd skills/alexa-sports-narrator/workflows

# Reinstall
machina install skills/alexa-sports-narrator --force
```

## Cost Optimization

1. **Cache frequently requested data**
2. **Use GPT-4o-mini instead of GPT-4o**
3. **Limit to free tier sports (trial APIs)**
4. **Implement rate limiting**
5. **Monitor CloudWatch metrics**

## Next Steps

- Add more sports (MLB, NHL)
- Implement voice synthesis with ElevenLabs
- Add proactive notifications
- Create dashboard for managing favorites
- Expand to Google Assistant

## Resources

- [Alexa Skills Kit Documentation](https://developer.amazon.com/docs/ask-overviews/build-skills-with-the-alexa-skills-kit.html)
- [AWS Lambda Python](https://docs.aws.amazon.com/lambda/latest/dg/lambda-python.html)
- [Sportradar API Docs](https://developer.sportradar.com)
- [Machina Templates Docs](../../README.md)
