# 1.5.5

- Added `Any` and `Dict` to generated model imports

# 1.5.4

- Pin click dependency to 8.1.8
- Added project documentation for Gemini CLI
- Added CODEOWNERS file
- Added GitHub Action for automated PyPI publishing

# 1.5.3

- Fixed repository links

# 1.5.2

- Fixed generated model naming bug

# 1.5.1

- Added optional Pydantic model generation via `--model-library pydantic` (requires `prismarine[pydantic]`)
- Generated clients can now convert DynamoDB payloads to/from `BaseModel` instances when the option is enabled
- Introduced unit tests that cover both TypedDict and Pydantic generation paths

# 1.4.2

- Fixed index decorator not recognizing models with a changed name

# 1.4.1

- Added support for DynamoDB Streams/Triggers

# 1.3.1

- Fixed json load encoding issue

# 1.3.0

- Added `extra-imports` option to `generate-client` command

# 1.2.0

- Added `prismarine version` command to print the version of Prismarine
- Changed `generate-client` command syntax to be more consistent with other commands
- Ensured deterministic generation of client code

# 1.1.0

- Integration with EasySAM
- Added export decorator

# 1.0.0

- First published version
