# PolicyEngine Household API

The PolicyEngine Household API computes taxes and benefits for a single household at a single point in time. Send a JSON description of the household, get back a JSON response with the values you asked for.

This guide is for partners integrating the API into client-facing tools — case-management software, eligibility screeners, financial planning calculators, and similar.

## Who this is for

If you maintain software that asks "what would *this specific household* receive in benefits or owe in taxes?", this API is the calculation engine you can call instead of writing those rules yourself. PolicyEngine maintains the rules; you call the endpoint.

This API does not run population-level microsimulations. For "how does this reform affect the country?", see the [PolicyEngine main API](https://policyengine.org/us/api).

## What you can do

- Compute taxes and benefits for any US, UK, Canadian, Israeli, or Nigerian household
- Use a single request, sent as JSON over HTTPS
- Send inputs annually or month by month, and request outputs at the same cadence
- Get a structured 400 response when the request is malformed, with the specific field that's wrong

## Status

This documentation is being written. The API itself is in production at `https://household.api.policyengine.org`. Pages marked _Coming soon_ below are next on the writing queue.

## Read next

- [Request format](request-format.md) — _Coming soon_
- [Period keys](period-keys.md) — _Coming soon_
- [Response format](response-format.md) — _Coming soon_
- [Cookbook](cookbook/index.md) — partner recipes (eligibility-cliff recipe is live)
- [Changelog](changelog.md) — _Coming soon_
