"""GraphQL queries for ingestion.

Shape notes (verified against GitHub's published schema — see ADR-008):

- `Repository.pullRequests` accepts **no `since` argument** (only `after/before/first/last/
  baseRefName/headRefName/labels/orderBy/states`), so incremental sync pages
  `orderBy: {field: UPDATED_AT, direction: DESC}` and the pipeline stops paging when it reaches
  items older than the watermark. The same is true of `Repository.issues`.
- `Commit.history` **does** accept `since`/`until`, so commits are filtered server-side.
- Reviews and files are nested in the PR query to avoid N+1 per-PR requests (blueprint §13.1).
  Nested connections are capped at 100 by GitHub; PRs larger than that get a follow-up
  file query (see `pipeline.py`).

`rateLimit` is requested on every query so the client can pause before the budget runs out.
"""

from __future__ import annotations

REPOSITORY_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    id
    nameWithOwner
    defaultBranchRef { name }
    pushedAt
    pullRequests { totalCount }
  }
  rateLimit { remaining cost limit resetAt }
}
"""

PULL_REQUESTS_QUERY = """
query($owner: String!, $name: String!, $first: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(first: $first, after: $after, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        id
        number
        title
        state
        isDraft
        createdAt
        updatedAt
        closedAt
        mergedAt
        author { id login isBot }
        additions
        deletions
        changedFiles
        baseRefName
        headRefName
        labels(first: 50) { nodes { name } }
        body
        reviews(first: 100) {
          nodes {
            id
            author { id login isBot }
            state
            submittedAt
          }
        }
        files(first: 100) {
          totalCount
          pageInfo { hasNextPage endCursor }
          nodes { path additions deletions }
        }
      }
    }
  }
  rateLimit { remaining cost limit resetAt }
}
"""

#: Follow-up query for PRs whose nested `files` connection was truncated at 100.
PR_FILES_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $first: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      files(first: $first, after: $after) {
        totalCount
        pageInfo { hasNextPage endCursor }
        nodes { path additions deletions }
      }
    }
  }
  rateLimit { remaining cost limit resetAt }
}
"""

ISSUES_QUERY = """
query($owner: String!, $name: String!, $first: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    issues(first: $first, after: $after, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        id
        number
        title
        state
        createdAt
        updatedAt
        closedAt
        author { id login isBot }
        labels(first: 50) { nodes { name } }
        body
        # `reopened_count`: counting REOPENED_EVENT timeline items per issue.
        timelineItems(first: 1, itemTypes: [REOPENED_EVENT]) { totalCount }
      }
    }
  }
  rateLimit { remaining cost limit resetAt }
}
"""

COMMITS_QUERY = """
query($owner: String!, $name: String!, $branch: String!, $first: Int!, $after: String,
      $since: GitTimestamp, $until: GitTimestamp) {
  repository(owner: $owner, name: $name) {
    ref(qualifiedName: $branch) {
      target {
        ... on Commit {
          history(first: $first, after: $after, since: $since, until: $until) {
            totalCount
            pageInfo { hasNextPage endCursor }
            nodes {
              id
              oid
              committedDate
              additions
              deletions
              isMerge
              message
              author {
                name
                email
                user { id login isBot }
              }
            }
          }
        }
      }
    }
  }
  rateLimit { remaining cost limit resetAt }
}
"""
