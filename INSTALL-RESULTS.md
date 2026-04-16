# Machina CLI Template Installation Results

## 1. Verify CLI Version
```text
machina-cli v0.2.23
```

## 2. Verify Project Configuration
```text
                                 Configuration                                  
┏━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Key                     ┃ Value                                              ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ api_url                 │ https://api.machina.gg                             │
│ client_api_url          │ https://machina-podcasts-machina-sports-podcast.o… │
│ default_organization_id │ 6876c6e319689bf880aa80b7                           │
│ default_project_id      │ 690d5c76ed71f2d5f9908108                           │
│ output_format           │ table                                              │
│ session_url             │ https://session.machina.gg                         │
└─────────────────────────┴────────────────────────────────────────────────────┘
```

## 3. Verify Template Exists
```text
ls: cannot access 'connectors/goalserve-soccer/': No such file or directory
```

## 4. Show Install Configuration
```yaml
cat: connectors/goalserve-soccer/_install.yml: No such file or directory
```

## 5. Push Template
```text
Directory not found: connectors/goalserve-soccer
```

## 6. Verify Connector Installed
```text
                                   Connectors                                   
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Name                              ┃ Type ┃ Status ┃ ID                       ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ adapters-builder-reasoning-contr… │      │ active │ 69e02c70d987fd684b85c31d │
│ adapters-builder-response-contro… │      │ active │ 69e02c70d987fd684b85c31e │
│ adapters-engine-deploy-controller │      │ active │ 69e02c70d987fd684b85c321 │
│ adapters-hf-train-controller      │      │ active │ 69e02c70d987fd684b85c320 │
│ adapters-hf-upload-controller     │      │ active │ 69e02c70d987fd684b85c31f │
│ adapters-inference-reasoning-con… │      │ active │ 69e02c70d987fd684b85c31b │
│ adapters-inference-response-cont… │      │ active │ 69e02c70d987fd684b85c31c │
│ american-football                 │      │ active │ 69e14e53ec1f7952e7867c82 │
│ api-football                      │      │ active │ 69e14e50ec1f7952e7867c25 │
│ api-mailgun                       │      │ active │ 690d617a1375ae74448e4664 │
│ assistant-tools-build-parlay      │      │ active │ 69e0d89d6d8ef32c11d02342 │
│ assistant-tools-event-id-collect… │      │ active │ 69e0d89d6d8ef32c11d0234c │
│ assistant-tools-map-markets       │      │ active │ 69e0d89d6d8ef32c11d02343 │
│ assistant-tools-map-stories       │      │ active │ 69e0d89d6d8ef32c11d02344 │
│ assistant-tools-market-event-mat… │      │ active │ 69e0d89d6d8ef32c11d0234b │
│ assistant-tools-persona-randomiz… │      │ active │ 69e0d89d6d8ef32c11d02345 │
│ assistant-tools-slack-formatter   │      │ active │ 69e0d89d6d8ef32c11d0232d │
│ bundesliga-podcast-compose        │      │ active │ 69e14e4bec1f7952e7867b9e │
│ bwin                              │      │ active │ 69e14e50ec1f7952e7867c37 │
│ bwin-grep-sports                  │      │ active │ 69e14e50ec1f7952e7867c39 │
└───────────────────────────────────┴──────┴────────┴──────────────────────────┘
```
