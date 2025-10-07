Implementation Plan
===================

**Server.py Architecture**
--------------------------

### Core Components:

1.  **TCP Socket Setup**

    -   Bind to localhost (127.0.0.1) and a configurable port (e.g., 5000)
    -   Listen for incoming connections
2.  **Connection Management**

    -   Track active connections (max 3 concurrent)
    -   Auto-assign client names: "Client01", "Client02", etc.
    -   Use threading to handle each client independently
3.  **Client Cache System**

    -   Dictionary storing: `{client_name: {connection_time, disconnect_time, address}}`
    -   In-memory only (no file persistence)
4.  **Message Handler**

    -   **Regular messages**: Echo back with " ACK" appended
    -   **"status"**: Return formatted cache contents
    -   **"list"**: Return list of files in server's repository folder
    -   **"exit"**: Clean disconnect and update cache
    -   **File requests**: Stream requested file to client (with error handling)
5.  **File Repository**

    -   Create a "server_files" directory
    -   Scan and list available files

**Client.py Architecture**
--------------------------

### Core Components:

1.  **Connection Setup**

    -   Connect to server (IP + port)
    -   Send assigned client name to server
2.  **CLI Interface**

    -   Continuous input loop
    -   Send messages to server
    -   Display server responses
3.  **Command Support**

    -   Regular text messages
    -   "status" command
    -   "list" command
    -   File download requests
    -   "exit" to disconnect
4.  **File Reception**

    -   Receive and save files to "client_downloads" directory
    -   Handle file transfer protocol

**Key Design Decisions**
------------------------

### Thread Safety:

-   Use threading.Lock() for client counter and cache updates

### File Transfer Protocol:

-   For file transfers: Send file size first, then file content
-   Use special delimiters to distinguish file data from messages

### Error Handling:

-   Handle connection drops gracefully
-   Validate file existence before streaming
-   Handle max client limit

### Code Style:

-   Clean, documented functions
-   Descriptive variable names
-   Comprehensive comments
-   Error handling for all network operations

* * * * *

**Testing Checklist** (per rubric):
-----------------------------------

1.  ✓ Server and client creation
2.  ✓ Auto-naming (Client01, Client02, etc.)
3.  ✓ Multi-threading support
4.  ✓ 3-client limit enforcement
5.  ✓ Message exchange with ACK
6.  ✓ Clean exit handling
7.  ✓ Client cache maintenance
8.  ✓ File listing
9.  ✓ File streaming

