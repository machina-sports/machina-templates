# YAML Formatting and Prettifying

The Machina Assistant provides a built-in capability to format and prettify YAML code blocks. This is particularly useful when working with Machina configurations for connectors, workflows, and agents, where correct indentation and structure are critical.

## Features

- **Indentation Correction**: Automatically fixes inconsistent indentation using a standard 2-space format.
- **Alignment**: Aligns keys and values for better readability.
- **Structure Validation**: Helps identify and correct structural issues in YAML definitions.
- **Machina Syntax Awareness**: Understands the specific structure of Machina configuration files.

## How to Use

To use the YAML formatter, simply paste your YAML code into the chat and ask the assistant to format it. For example:

- "Format this YAML for me: [your code here]"
- "Prettify this connector definition: [your code here]"
- "Fix the indentation in this workflow: [your code here]"

## Best Practices

- **Paste Full Blocks**: For the best results, paste the entire YAML block you want to format.
- **Specify the Component**: If the YAML is for a specific Machina component (like a connector or workflow), mentioning it helps the assistant provide better context.
- **Review Changes**: Always review the formatted YAML to ensure the logic remains as intended.

## Example

### Input (Messy YAML)
```yaml
connector:
  name: "my-connector"
 description: "A messy description"
  commands:
   - name: "Command 1"
    value: "cmd1"
```

### Output (Formatted YAML)
```yaml
connector:
  name: "my-connector"
  description: "A messy description"
  commands:
    - name: "Command 1"
      value: "cmd1"
```

