# ---------------------------------------------------------------------------
# Sourced by start.sh and worker.sh before they exec the process.
#
# PUBLIC_APP_URL is the origin every link in outbound email points at. Its
# default is http://localhost:3000, which is right on a laptop and silently
# wrong in a deployed inbox: the mail sends, and the link goes nowhere.
# Settings cannot tell a real origin from a forgotten default, so a deployed
# environment checks here and refuses to boot rather than mail localhost to
# customers.
#
# Development and test are left alone — localhost is the right answer there.
# ---------------------------------------------------------------------------

case "${ENVIRONMENT:-development}" in
  staging|production)
    _url="${PUBLIC_APP_URL:-}"
    case "$_url" in
      "")
        echo "entrypoint: PUBLIC_APP_URL is required when ENVIRONMENT=${ENVIRONMENT}" >&2
        exit 1
        ;;
      https://localhost*|https://127.*|https://0.0.0.0*|https://*.local|https://*.local/*|https://*.local:*)
        echo "entrypoint: PUBLIC_APP_URL=${_url} is not a public origin" >&2
        exit 1
        ;;
      https://?*)
        ;;
      *)
        echo "entrypoint: PUBLIC_APP_URL=${_url} must be the https:// frontend origin" >&2
        exit 1
        ;;
    esac
    unset _url
    ;;
esac
