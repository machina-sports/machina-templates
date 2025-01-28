# Newsletter Agentic System

### Overview
This system is designed to automate the process of generating personalized newsletters using user-specific data and external information sources. It integrates multiple workflows that analyze users, collect relevant topics, and produce a final newsletter using a combination of prompt-based AI models and web search results.

### Features
- **User Registration Workflow:** Registers users for newsletters and saves their preferences for future personalization.
- **Topic Analysis Workflow:** Analyzes user data, including preferences for athletes, teams, competitions, and sports, to generate topic descriptions for newsletters.
- **Web Search Integration:** Utilizes web search to gather the latest news and content related to the topics of interest.
- **AI-Generated Content:** Leverages GPT-4 models to generate summaries and content based on collected data and web search results.
- **Newsletter Review Workflow:** A final revision process that ensures the content is tailored and accurate before sending it to users.

### Agent Workflow

The following workflows are used in the system to manage user data and generate personalized newsletters:

1. **Save User in Newsletter (workflow-save-user)**
   - **Description:** Saves the user's information in the newsletter system.

2. **Generate Athletes Resume (workflow-topic-analysis)**
   - **Description:** Generates a resume based on the user's preferences for athletes.

3. **Generate Competitions Resume (workflow-topic-analysis)**
   - **Description:** Generates a resume based on the user's preferences for competitions.

4. **Generate Teams Resume (workflow-topic-analysis)**
   - **Description:** Generates a resume based on the user's preferences for teams.

5. **Generate Sports Resume (workflow-topic-analysis)**
   - **Description:** Generates a resume based on the user's preferences for sports.

6. **Generate Subjects Resume (workflow-topic-analysis)**
   - **Description:** Generates a resume based on the user's preferences for subjects.

7. **Generate User Newsletter (workflow-topic-review)**
   - **Description:** Reviews and generates the final version of the newsletter to be sent to the user.

### Workflow Diagram

Here is a visual representation of the agent workflow:

![Workflow Diagram](datasets/templates/newsletter/_workflow.png)

### Workflow Breakdown

#### Workflow 1: Save User in Newsletter (`workflow-save-user`)

1. **Prompt**: `prompt-profile-analysis`
  - **Description**: Analyzes the user’s profile to gather necessary information for newsletter personalization.

2. **Document**: `task-save-user`
  - **Description**: Saves the user's information and preferences in the system.

#### Workflow 2: Topic Analysis (`workflow-topic-analysis`)

1. **Prompt**: `prompt-topic-analysis`
  - **Description**: Analyzes topics based on user preferences, including athletes, teams, competitions, sports, and subjects.

2. **Connector**: `task-topic-websearch`
  - **Description**: Conducts a web search to find relevant news articles about the topics of interest.

3. **Prompt**: `prompt-generate-newsletter`
  - **Description**: Generates a draft of the newsletter based on the user's preferences and the web search results.

#### Workflow 3: Review Newsletter (`workflow-topic-review`)

1. **Prompt**: `prompt-review-newsletter`
  - **Description**: Reviews the generated newsletter to ensure content accuracy and alignment with user preferences before sending it.

---

Each workflow has been designed to guide the system from user data analysis to the generation and review of the newsletter, ensuring personalized and up-to-date content.


### Installation

To install and set up the system, run the following `curl` command. This will load the necessary datasets for agents, prompts, and workflows.

```bash
curl --location 'http://127.0.0.1:5001/dataset' \
--header 'Content-Type: application/json' \
--header 'Authorization: ••••••' \
--data '[
  {
    "dataset_type": "agent",
    "dataset_name": "templates/newsletter/agent-registration"
  },
  {
    "dataset_type": "prompts",
    "dataset_name": "templates/newsletter/prompt-newsletter"
  },
  {
    "dataset_type": "workflow",
    "dataset_name": "templates/newsletter/workflow-save-user"
  },
  {
    "dataset_type": "workflow",
    "dataset_name": "templates/newsletter/workflow-topic-analysis"
  },
  {
    "dataset_type": "workflow",
    "dataset_name": "templates/newsletter/workflow-topic-revise"
  }
]'
```

### Running the Agent

To execute the system, you can use the following `curl` command. This command triggers the `agent-registration` workflow by passing user information and relevant API keys.

```bash
curl --location 'http://127.0.0.1:5001/agent/executor/agent-registration' \
--header 'Content-Type: application/json' \
--header 'Authorization: ••••••' \
--data-raw '{
    "agent-config": {
        "delay": false
    },
    "context-agent": {
        "user-object": {
            "name": "Fernando",
            "email": "fernando@machina.gg",
            "interests": "UEFA Champions League, Formula 1"
        }
    },
    "context-variables": {
        "api-football": {
            "api_key": "$TEMP_CONTEXT_VARIABLE_API_FOOTBALL_API_KEY"
        },
        "sdk-audio": {
            "api_key": "$TEMP_CONTEXT_VARIABLE_SDK_AUDIO_API_KEY"
        },
        "sdk-openai": {
            "api_key": "$TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY"
        },
        "sdk-serper": {
            "api_key": "$TEMP_CONTEXT_VARIABLE_SERPER_API_KEY"
        }
    }
}'
```
