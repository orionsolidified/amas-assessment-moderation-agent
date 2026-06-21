Review the following verified specialist findings.

CASE SUMMARY:
{{CASE_BUNDLE_JSON}}

VERIFIED FINDINGS:
{{VERIFIED_FINDINGS_JSON}}

REJECTED OR WEAK FINDINGS:
{{REJECTED_FINDINGS_JSON}}

Return one JSON object with:
- finding_reviews: array of {finding_ref, action: uphold|revise|downgrade|reject, revised_severity, concise_reason, revised_recommendation};
- missing_analyses: array;
- systemic_risks: array;
- critic_summary: string.
