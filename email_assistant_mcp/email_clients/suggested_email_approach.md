# Gmail Batch Move Implementation Guide

## Overview

This document outlines the implementation of efficient message moving operations in the MCP server using Gmail API's batch HTTP requests. This approach allows moving multiple messages with different label configurations in a single API call.

## Current Context

- **System**: MCP server managing Gmail mailbox
- **Component**: Dedicated Gmail client
- **Requirement**: Move multiple messages with different labels efficiently
- **Solution**: Implement Gmail API batch HTTP requests for `messages.modify` operations

## The Problem

When moving messages in Gmail (which uses labels, not folders), each message may need:
- Different destination labels added
- Different source labels removed
- Individual treatment based on business logic

Sequential API calls result in:
- High latency (50-100ms per message × N messages)
- Excessive network overhead
- Poor user experience for bulk operations
- Inefficient resource usage

## The Solution: Batch HTTP Requests

Gmail API supports batching up to 100 individual API calls into a single multipart HTTP request. Each sub-request can have different parameters, making it perfect for moving messages with different label configurations.

### Performance Benefits

| Metric | Sequential (100 msgs) | Batch (100 msgs) | Improvement |
|--------|----------------------|------------------|-------------|
| Round trips | ~100 | ~1 | 100x |
| Time (50ms latency) | 5 seconds | 0.05 seconds | 100x faster |
| HTTP overhead | 100× headers | 1× headers | 99% reduction |
| Throughput | 10-20 msg/sec | 200-1000 msg/sec | 10-100x |

## Implementation Approach

### 1. Batch Request Structure

```http
POST https://gmail.googleapis.com/batch/gmail/v1
Authorization: Bearer {access_token}
Content-Type: multipart/mixed; boundary={boundary_string}

--{boundary_string}
Content-Type: application/http
Content-ID: <item1>

POST /gmail/v1/users/me/messages/{message_id_1}/modify
Content-Type: application/json

{
  "addLabelIds": ["Label_XXX", "Label_YYY"],
  "removeLabelIds": ["INBOX"]
}

--{boundary_string}
Content-Type: application/http
Content-ID: <item2>

POST /gmail/v1/users/me/messages/{message_id_2}/modify
Content-Type: application/json

{
  "addLabelIds": ["Label_ZZZ"],
  "removeLabelIds": ["INBOX", "UNREAD"]
}

--{boundary_string}--
```

### 2. Input Format

The MCP server should accept an array of message operations:

```json
[
  {
    "message_id": "2632762",
    "addLabelIds": ["INBOX", "Label_Shopping"],
    "removeLabelIds": []
  },
  {
    "message_id": "26327644",
    "addLabelIds": ["Label_Tennis"],
    "removeLabelIds": ["INBOX"]
  }
]
```

### 3. Key Implementation Details

#### Boundary String
- Must be unique for each request
- Should not appear in the content
- Suggested format: `batch_boundary_{timestamp}` or `batch_boundary_{uuid}`

#### Content-ID
- Optional but recommended for matching responses to requests
- Format: `<item{index}>` or `<msg_{message_id}>`
- Helps identify which response corresponds to which request

#### Relative Paths
- Use `/gmail/v1/users/me/messages/{id}/modify`
- NOT full URLs (no `https://gmail.googleapis.com` prefix)

#### Authorization
- Only needed in the outer request header
- Do NOT include Authorization in individual sub-requests

#### Label IDs vs Names
- System labels: Use uppercase names (`INBOX`, `SENT`, `TRASH`, `SPAM`, `UNREAD`)
- Custom labels: Use label IDs (e.g., `Label_123456789`)
- Must call `users.labels.list` to map label names to IDs

### 4. Response Structure

```http
HTTP/1.1 200 OK
Content-Type: multipart/mixed; boundary=batch_response_boundary

--batch_response_boundary
Content-Type: application/http
Content-ID: <response-item1>

HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "2632762",
  "threadId": "...",
  "labelIds": ["INBOX", "Label_Shopping"]
}

--batch_response_boundary
Content-Type: application/http
Content-ID: <response-item2>

HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "26327644",
  "threadId": "...",
  "labelIds": ["Label_Tennis"]
}

--batch_response_boundary--
```

### 5. Error Handling

**Important**: Each sub-request can succeed or fail independently.

Example partial failure:

```http
--batch_response_boundary
Content-Type: application/http
Content-ID: <response-item1>

HTTP/1.1 200 OK
Content-Type: application/json

{"id": "2632762", ...}

--batch_response_boundary
Content-Type: application/http
Content-ID: <response-item2>

HTTP/1.1 404 NOT FOUND
Content-Type: application/json

{
  "error": {
    "code": 404,
    "message": "Message not found",
    "status": "NOT_FOUND"
  }
}

--batch_response_boundary--
```

## Implementation Steps for MCP Server

### Step 1: Add Batch Move Method to Gmail Client

Create a new method in your Gmail client class:

```python
def batch_modify_messages(self, message_updates: List[Dict]) -> Dict:
    """
    Batch modify multiple messages with different label configurations.
    
    Args:
        message_updates: List of dicts with structure:
            {
                "message_id": str,
                "addLabelIds": List[str],
                "removeLabelIds": List[str]
            }
    
    Returns:
        Dict containing:
            - success: List of successfully modified message IDs
            - failures: List of failed operations with error details
            - results: Full parsed response data
    """
```

### Step 2: Implement Request Builder

```python
def _build_batch_request_body(self, message_updates: List[Dict], boundary: str) -> str:
    """Build multipart batch request body."""
    batch_body = ""
    
    for i, update in enumerate(message_updates):
        batch_body += f"--{boundary}\r\n"
        batch_body += "Content-Type: application/http\r\n"
        batch_body += f"Content-ID: <item{i}>\r\n\r\n"
        
        batch_body += f"POST /gmail/v1/users/me/messages/{update['message_id']}/modify\r\n"
        batch_body += "Content-Type: application/json\r\n\r\n"
        
        modify_request = {}
        if update.get('addLabelIds'):
            modify_request['addLabelIds'] = update['addLabelIds']
        if update.get('removeLabelIds'):
            modify_request['removeLabelIds'] = update['removeLabelIds']
        
        batch_body += json.dumps(modify_request) + "\r\n"
    
    batch_body += f"--{boundary}--"
    return batch_body
```

### Step 3: Implement Response Parser

```python
def _parse_batch_response(self, response_text: str) -> Dict:
    """
    Parse multipart batch response.
    
    Returns:
        {
            "success": [{"message_id": "...", "labelIds": [...], ...}, ...],
            "failures": [{"message_id": "...", "error": {...}, ...}, ...]
        }
    """
    success = []
    failures = []
    
    # Parse multipart response
    # Extract boundary from Content-Type header
    # Split response by boundary
    # For each part:
    #   - Extract HTTP status code
    #   - Extract JSON body
    #   - Categorize as success or failure
    
    return {
        "success": success,
        "failures": failures
    }
```

### Step 4: Handle Label Name to ID Mapping

```python
def _resolve_label_ids(self, label_names: List[str]) -> List[str]:
    """
    Convert label names to label IDs.
    
    System labels (INBOX, SENT, etc.) remain unchanged.
    Custom labels are resolved via labels.list API call.
    Cache results to minimize API calls.
    """
    label_ids = []
    
    for name in label_names:
        # System labels use uppercase names directly
        if name.upper() in ['INBOX', 'SENT', 'TRASH', 'SPAM', 'UNREAD', 'STARRED', 'IMPORTANT', 'DRAFT']:
            label_ids.append(name.upper())
        else:
            # Resolve custom label name to ID
            label_id = self._get_label_id_by_name(name)
            if label_id:
                label_ids.append(label_id)
    
    return label_ids
```

### Step 5: Add MCP Command

Update your MCP server to expose the batch move functionality:

```python
@mcp_server.tool()
def batch_move_messages(
    message_operations: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Move multiple messages with different label configurations.
    
    Args:
        message_operations: List of operations, each containing:
            - message_id: Gmail message ID
            - add_labels: List of label names to add
            - remove_labels: List of label names to remove
    
    Returns:
        Summary of operations with success/failure counts and details
    """
    # Resolve label names to IDs
    # Build batch request
    # Execute batch request
    # Parse and return results
```

## Optimization Considerations

### 1. Batching Strategy

**Optimal batch size**: 50-100 messages per batch
- Too small: Doesn't fully leverage batching benefits
- Too large: Risk of timeout, harder error recovery

**For >100 messages**: Split into multiple batches and execute sequentially or with controlled concurrency.

### 2. Label Caching

Cache label name-to-ID mappings:
- Refresh periodically (e.g., every 5 minutes)
- Invalidate on label-related operations
- Reduces API calls significantly

### 3. Retry Logic

Implement retry for transient failures:
- Network timeouts
- Rate limit errors (503)
- Server errors (500, 502, 503)

**Do NOT retry**: 
- 400 Bad Request (fix the request)
- 404 Not Found (message doesn't exist)
- 403 Forbidden (permission issues)

### 4. Progress Reporting

For large batches (50+ messages), consider:
- Splitting into smaller batches
- Reporting progress after each batch
- Allowing cancellation between batches

## Testing Strategy

### Unit Tests

1. **Request builder tests**:
   - Verify correct multipart format
   - Test boundary uniqueness
   - Validate Content-ID generation

2. **Response parser tests**:
   - Parse successful responses
   - Parse partial failures
   - Handle malformed responses

3. **Label resolution tests**:
   - System labels pass through unchanged
   - Custom labels resolve correctly
   - Handle missing labels gracefully

### Integration Tests

1. **Small batch (1-5 messages)**:
   - Verify all succeed
   - Verify correct labels applied

2. **Large batch (50+ messages)**:
   - Test performance improvement
   - Verify all processed

3. **Partial failure scenarios**:
   - Mix of valid/invalid message IDs
   - Some messages already have target labels
   - Some labels don't exist

4. **Edge cases**:
   - Empty batch
   - Duplicate message IDs
   - Message with no label changes

## Migration Path

### Phase 1: Implement Batch Method
- Add batch method to Gmail client
- Keep existing sequential method as fallback
- Add feature flag to control usage

### Phase 2: Test with Small Volumes
- Enable for batches of 5-10 messages
- Monitor success rates and performance
- Gather error patterns

### Phase 3: Gradual Rollout
- Increase batch size gradually
- Monitor rate limits and errors
- Tune retry logic and timeouts

### Phase 4: Full Migration
- Make batch the default for 2+ messages
- Remove/deprecate sequential method
- Update documentation

## API Quota Considerations

**Important**: Batch requests count toward quota!
- 1 batch with 100 modify operations = 100 quota units
- Batching doesn't reduce quota usage
- Batching improves latency and throughput, not quota

**Gmail API Quotas** (as of 2024):
- Per-user rate limit: 250 quota units/user/second
- Daily quota: Check your Google Cloud Console

**Best Practices**:
- Monitor quota usage
- Implement exponential backoff for rate limit errors
- Consider user-level rate limiting if needed

## Security Considerations

1. **OAuth Token Handling**:
   - Only include in outer request header
   - Never log tokens
   - Refresh tokens before expiration

2. **Input Validation**:
   - Validate message IDs format
   - Sanitize label names
   - Limit batch size (max 100)

3. **Error Information**:
   - Don't expose internal errors to end users
   - Log detailed errors server-side
   - Return sanitized error messages

## Monitoring and Logging

### Metrics to Track

1. **Performance**:
   - Average batch processing time
   - Throughput (messages/second)
   - 95th/99th percentile latency

2. **Success Rates**:
   - Overall success rate
   - Success rate per message
   - Failure reasons breakdown

3. **Batch Characteristics**:
   - Average batch size
   - Distribution of batch sizes
   - Time between batches

### Logging

Log the following for each batch operation:

```json
{
  "timestamp": "2024-12-17T10:30:00Z",
  "operation": "batch_modify_messages",
  "batch_size": 50,
  "success_count": 48,
  "failure_count": 2,
  "duration_ms": 250,
  "failures": [
    {
      "message_id": "123",
      "error_code": 404,
      "error_message": "Message not found"
    }
  ]
}
```

## Example Implementation Pseudocode

```python
class GmailBatchClient:
    def __init__(self, credentials):
        self.credentials = credentials
        self.label_cache = {}
        self.batch_endpoint = "https://gmail.googleapis.com/batch/gmail/v1"
    
    def batch_move_messages(self, operations):
        """
        operations = [
            {
                "message_id": "123",
                "add_labels": ["Shopping", "Important"],
                "remove_labels": ["Inbox"]
            },
            ...
        ]
        """
        # Step 1: Resolve label names to IDs
        resolved_ops = self._resolve_labels(operations)
        
        # Step 2: Split into batches of 100
        batches = self._split_into_batches(resolved_ops, batch_size=100)
        
        # Step 3: Process each batch
        all_results = []
        for batch in batches:
            result = self._process_batch(batch)
            all_results.append(result)
        
        # Step 4: Aggregate and return results
        return self._aggregate_results(all_results)
    
    def _process_batch(self, operations):
        # Generate unique boundary
        boundary = f"batch_boundary_{uuid.uuid4()}"
        
        # Build request body
        body = self._build_batch_body(operations, boundary)
        
        # Send request
        response = requests.post(
            self.batch_endpoint,
            headers={
                "Authorization": f"Bearer {self.credentials.token}",
                "Content-Type": f"multipart/mixed; boundary={boundary}"
            },
            data=body
        )
        
        # Parse response
        return self._parse_response(response.text)
    
    def _build_batch_body(self, operations, boundary):
        # Implementation as shown earlier
        pass
    
    def _parse_response(self, response_text):
        # Implementation as shown earlier
        pass
```

## References

- [Gmail API Batch Requests Documentation](https://developers.google.com/gmail/api/guides/batch)
- [Gmail API Messages.modify](https://developers.google.com/gmail/api/reference/rest/v1/users.messages/modify)
- [Gmail API Labels](https://developers.google.com/gmail/api/guides/labels)
- [Google API Batch Requests (General)](https://cloud.google.com/apis/docs/batch)

## Summary

Implementing batch requests for message moving operations provides:
- **100x performance improvement** for bulk operations
- **Reduced network overhead** and better resource usage
- **Flexibility** to apply different labels to different messages
- **Better user experience** with faster processing

The implementation requires:
- Multipart HTTP request construction
- Response parsing with error handling
- Label name-to-ID resolution and caching
- Proper retry logic and monitoring

This approach is essential for any production Gmail integration handling bulk message operations.