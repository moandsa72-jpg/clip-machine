# Standalone Campaign Finder Test

This workflow runs only `campaign-radar/campaign_scanner.py`. It does not run clip creation, rendering, validation, or publishing.

## Run it

1. Open the repository's **Actions** tab.
2. Select **Test Campaign Finder** in the workflow list on the left.
3. Choose **Run workflow** and keep the default config path.
4. Open the run and download the `campaign-finder-test-report` artifact.

The report is written to `campaign-radar/testing/latest.json`, not the production `campaign-radar/latest.json`. The workflow uses public pages and makes no paid API calls.
