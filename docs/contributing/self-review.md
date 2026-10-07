# Self review

You should always review your own PR before submitting it.

For content changes make sure that you:

-   [x] Confirm that the changes meet the user experience and goals outlined in the content design plan (if there is
        one).
-   [x] Compare your changes to the `beta` branch to confirm that the output matches the source and that everything is
        working as expected.
-   [x] Review the entire pull request for typos in comments and doctrings.
-   [x] If there are any failing checks in your PR, troubleshoot them until they are all passing.
-   [x] Make sure your pull request targets the `beta` branch and that the prefix of its title reflects the nature
        of the change, the [version number](./versioning.md) is derived from it. Leave `odev/_version.py` untouched.
