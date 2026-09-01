# Test-specific agent rules
- Tests must use synthetic/de-identified fixtures only.
- A test failing because a product rule changed requires a versioned spec/policy change; do not weaken assertions silently.
- Critical invariants need negative/adversarial cases, not only happy paths.
- OCR tests separate extraction accuracy, locus association, and abstention.
