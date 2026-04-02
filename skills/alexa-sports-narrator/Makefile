# Alexa Sports Narrator - Deployment Makefile
#
# Usage:
#   make build-lambda          # Build deployment ZIP from scratch
#   make update-lambda         # Fast update: add only lambda_function.py to existing ZIP
#   make deploy-lambda         # Deploy ZIP to AWS Lambda (requires AWS CLI)
#   make install-workflows     # Install workflows + connectors to Machina server
#   make deploy-all            # Full deploy: build + deploy + install workflows
#
# Required env vars for deploy-lambda:
#   FUNCTION_NAME  (default: alexa-sports-narrator)
#   AWS_REGION     (default: us-east-1)

FUNCTION_NAME ?= alexa-sports-narrator
AWS_REGION    ?= sa-east-1
LAMBDA_DIR    := lambda
DIST_ZIP      := $(LAMBDA_DIR)/deployment.zip
BASE_ZIP      := $(LAMBDA_DIR)/alexa-sports-narrator-lambda.zip
SKILL_ROOT    := $(shell git rev-parse --show-toplevel)/skills/alexa-sports-narrator

.PHONY: build-lambda update-lambda deploy-lambda install-workflows deploy-all clean help

help:
	@echo ""
	@echo "Alexa Sports Narrator - Deploy targets:"
	@echo "  make build-lambda       Build deployment ZIP from scratch (installs deps)"
	@echo "  make update-lambda      Fast update: just replaces lambda_function.py in ZIP"
	@echo "  make deploy-lambda      Deploy ZIP to AWS Lambda"
	@echo "  make install-workflows  Install workflows + connectors to Machina server"
	@echo "  make deploy-all         build-lambda + deploy-lambda + install-workflows"
	@echo ""

## Build full package (installs Python deps + lambda code)
build-lambda:
	@echo "==> Building Lambda deployment package..."
	rm -rf $(LAMBDA_DIR)/package $(DIST_ZIP)
	pip install -r $(LAMBDA_DIR)/requirements.txt -t $(LAMBDA_DIR)/package --quiet
	cp $(LAMBDA_DIR)/lambda_function.py $(LAMBDA_DIR)/package/
	cd $(LAMBDA_DIR)/package && zip -r ../deployment.zip . -x "*.pyc" -x "*/__pycache__/*" -x "*.dist-info/*"
	@echo "==> Built: $(DIST_ZIP) ($$(du -sh $(DIST_ZIP) | cut -f1))"

## Fast update: take existing base ZIP and just replace lambda_function.py
## Use this after code-only changes (no new dependencies)
update-lambda:
	@echo "==> Fast update: adding lambda_function.py to existing ZIP..."
	@if [ ! -f "$(BASE_ZIP)" ]; then \
		echo "ERROR: $(BASE_ZIP) not found. Run 'make build-lambda' first."; \
		exit 1; \
	fi
	cp $(BASE_ZIP) $(DIST_ZIP)
	cd $(LAMBDA_DIR) && zip -g deployment.zip lambda_function.py
	@echo "==> Updated: $(DIST_ZIP) ($$(du -sh $(DIST_ZIP) | cut -f1))"

## Deploy the ZIP to AWS Lambda
deploy-lambda: $(DIST_ZIP)
	@echo "==> Deploying to AWS Lambda function: $(FUNCTION_NAME) ($(AWS_REGION))..."
	aws lambda update-function-code \
		--function-name $(FUNCTION_NAME) \
		--zip-file fileb://$(DIST_ZIP) \
		--region $(AWS_REGION)
	@echo "==> Waiting for update to complete..."
	aws lambda wait function-updated \
		--function-name $(FUNCTION_NAME) \
		--region $(AWS_REGION)
	@echo "==> Deploy complete."

## Install workflows and connectors to Machina server
install-workflows:
	@echo "==> Installing Alexa Sports Narrator workflows to Machina..."
	cd $(shell git rev-parse --show-toplevel) && machina install skills/alexa-sports-narrator --force
	@echo "==> Workflows installed."

## Full deploy cycle
deploy-all: update-lambda deploy-lambda install-workflows
	@echo ""
	@echo "==> Full deploy complete!"
	@echo "    Test with: aws lambda invoke --function-name $(FUNCTION_NAME) --payload file://test-event.json /tmp/response.json"

clean:
	rm -f $(DIST_ZIP)
	rm -rf $(LAMBDA_DIR)/package
	@echo "==> Cleaned build artifacts."

## Guard: ensure deployment.zip exists before deploying
$(DIST_ZIP):
	$(MAKE) update-lambda
