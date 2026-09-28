# Evolus Business Agent on AMD

A prototype for customer support and refund triage. Paste a customer email, extract the relevant facts with a local or OpenAI-compatible open-weight model, apply a deterministic refund policy, and review a drafted response.

 How it works

1. The model extracts the customer name, order ID, purchase date, item condition, and request summary from the email.
2. Python applies the business rules. Refunds are automatically approved only when the purchase is no more than 30 days old and the item is unopened. A purchase older than 30 days, an opened item, or missing/invalid facts requires human review.
3. The model drafts a customer email based on the decision. Human-review drafts acknowledge the request without promising or denying a refund.

The model does not make the eligibility decision. This keeps the policy consistent and auditable while leaving language understanding and drafting to the model.

 Tech stack

- Python and Streamlit for the interactive web app
- Pydantic for validating extracted facts
- Requests for the OpenAI-compatible chat completions API
- Ollama with an open-weight model such as Llama 3.1, or another compatible endpoint

 Run locally

1. Create and activate a Python virtual environment, then install dependencies:

   ```bash
   python -m venv .venv
   # Windows PowerShell
   .\.venv\Scripts\Activate.ps1
   # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Start Ollama and make sure the model is available. For example:

   ```bash
   ollama pull llama3.1
   ollama serve
   ```

   Ollama's OpenAI-compatible base URL defaults to `http://localhost:11434/v1`.

3. Launch the app:

   ```bash
   streamlit run app.py
   ```

4. Paste a support email into the app and select **Analyze request**. Configure the endpoint and model in the sidebar as needed.

## Configuration

The sidebar accepts the endpoint base URL and model name. Defaults can also be supplied through `OPENAI_BASE_URL` and `OPENAI_MODEL` environment variables. The app appends `/chat/completions` to the base URL, so enter the base (for example, `http://localhost:11434/v1`), not the full route.

## Policy boundary

- **Refund Approved:** purchase date is 0-30 days old, inclusive, and item condition is confirmed unopened.
- **Review Required:** purchase is older than 30 days, item is opened, date/condition is unknown, or the date is in the future.

This is a prototype, not a payment system, verify extracted facts and approve operational refunds before processing.