import socket
import threading
import os
from datetime import datetime


# Global variables 
client_counter = 0          
client_cache = {}           # Dictionary storing connection history: {client_name: {address, connected_at, disconnected_at}}
cache_lock = threading.Lock()  # Lock to protect client_cache and client_counter from race conditions


MAX_CLIENTS = 3                    
active_clients = 0                 
active_client_lock = threading.Lock()   

shutdown_event = threading.Event()      # Event to signal all threads to shutdown gracefully


HOST = '127.0.0.1'         
serverPort = 12000         
BUFFER_SIZE = 4096          # Buffer size for socket recv/send operations
FILE_REPO = 'server_files'  # Directory containing files available for download




def initialize_file_repo():
    """
    Ensures the file repository directory exists and creates it if it doesn't.
    
    This function is called once during server startup. If the repository directory
    doesn't exist, it creates it and populates it with sample text files for
    demonstration purposes.
    
    Side Effects:
        - Creates FILE_REPO directory if it doesn't exist
        - Creates sample files (file1.txt, file2.txt, file3.txt) in the directory
        - Prints status messages to console
    """
    if not os.path.exists(FILE_REPO):
        os.makedirs(FILE_REPO)
        print(f"[Server] Created directory: {FILE_REPO}")
        
        # Create sample files for testing and demonstration
        sample_files = ['file1.txt', 'file2.txt', 'file3.txt']
        for filename in sample_files:
            filepath = os.path.join(FILE_REPO, filename)
            with open(filepath, 'w') as f:
                f.write(f"This is {filename}, created for CP372 Assignment demonstration.\n")
        print(f"[Server] Sample files created in {FILE_REPO}")


def get_file():
    """
    Retrieves a list of all files in the server's file repository.
    
    This function scans the FILE_REPO directory and returns only regular files
    (not directories or special files).
    
    Returns:
        list: List of filenames (strings) in the repository
              Returns empty list if directory access fails
    """
    try:
        # List comprehension filters for files only (excludes directories)
        files = [f for f in os.listdir(FILE_REPO) if os.path.isfile(os.path.join(FILE_REPO, f))]
        return files
    except Exception as e:
        print(f"[Server] Error accessing file repository: {e}")
        return []


def send_file(client_socket, filename):
    """
    Streams a requested file to the client using a custom file transfer protocol.
    
    Protocol:
        1. Server sends header: "FILE_START|filename|size"
        2. Server waits for client acknowledgment: "READY"
        3. Server streams file content in chunks of BUFFER_SIZE bytes
    """
    # Construct full file path
    filepath = os.path.join(FILE_REPO, filename)

    if not os.path.exists(filepath):
        client_socket.send(b"ERROR: File not available.")
        return

    try:
        # Step 1: Get file size for transfer protocol
        file_size = os.path.getsize(filepath)

        # Step 2: Send file metadata header
        # Format: "FILE_START|filename|size" (pipe-delimited)
        header = f"FILE_START|{filename}|{file_size}".encode()
        client_socket.send(header)

        # Step 3: Wait for client acknowledgment to ensure synchronization
        ack = client_socket.recv(BUFFER_SIZE).decode()
        if ack != "READY":
            return 
        
        # Step 4: Stream file content in chunks
        with open(filepath, 'rb') as f:  # Open in binary mode for all file types
            bytes_sent = 0
            # Continue until entire file is sent or shutdown is requested
            while bytes_sent < file_size and not shutdown_event.is_set():
                # Read chunk (up to BUFFER_SIZE bytes)
                data = f.read(BUFFER_SIZE)
                if not data:
                    break
                # Send chunk over socket
                client_socket.send(data)
                bytes_sent += len(data)

        print(f"[Server] Finished sending file: {filename} ({bytes_sent} bytes)")
        
    except Exception as e:
        print(f"[Server] Error sending file: {e}")
        client_socket.send(b"ERROR: File transfer failed.")


def handle_socket_client(client_socket, client_address):
    """
    Handles all communication with a connected client in a separate thread.
    
    This function runs in its own thread for each client connection. It handles:
    - Client name assignment
    - Cache entry creation
    - Message processing (commands and regular messages)
    - File transfer requests
    - Connection cleanup
    
    Args:
        client_socket (socket.socket): Socket object for the client connection
        client_address (tuple): Client's address as (IP, port)
    
    Thread Safety:
        - Uses cache_lock when accessing client_cache and client_counter
        - Uses active_client_lock when modifying active_clients
    
    Commands Handled:
        - "exit": Disconnect client gracefully
        - "status": Return server's connection cache
        - "list": Return list of available files
        - "download:filename": Initiate file transfer
        - Any other text: Echo back with " ACK" appended
    """
    global client_counter, active_clients
    client_name = None
    
    # Set socket timeout to allow checking shutdown_event periodically
    client_socket.settimeout(1.0)

    try:
        # Assign unique client name and create cache entry (thread-safe)
        with cache_lock:
            client_counter += 1
            client_name = f"Client{client_counter:02d}"  # Format: Client01, Client02, etc.

            client_cache[client_name] = {
                'address': client_address,
                'connected_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'disconnected_at': None  # Will be updated on disconnect
            }
        
        # Send assigned name to client
        client_socket.send(client_name.encode())

        print(f"[Connected] {client_name} from {client_address}")
        print(f"[Info] Active clients: {active_clients}/{MAX_CLIENTS}")

        # Continue until client disconnects or server shuts down
        while not shutdown_event.is_set():
            try:
                message = client_socket.recv(BUFFER_SIZE).decode().strip()

                if not message:
                    break

                print(f"[{client_name}] Received: {message}")
                
                # Command: EXIT - Client wants to disconnect
                if message.lower() == "exit":
                    response = "BYE BYE! ACK"
                    client_socket.send(response.encode())
                    print(f"[Disconnect] {client_name} requested exit")
                    break
                
                # Command: STATUS - Client requests cache information
                elif message.lower() == "status":
                    status_info = format_cache()
                    client_socket.send(status_info.encode())
                    print(f"[Status] Sent cache status to {client_name}")

                # Command: LIST - Client requests available files
                elif message.lower() == "list":
                    files = get_file()
                    if files:
                        file_list = "Available files:\n" + "\n".join(f"  - {f}" for f in files)
                    else:
                        file_list = "No files available in repository"
                    client_socket.send(file_list.encode())
                    print(f"[List] Sent file list to {client_name}")

                # Command: DOWNLOAD - Client requests file transfer
                elif message.startswith("download:"):
                    # Extract filename after colon
                    filename = message.split(":", 1)[1].strip()
                    print(f"[Download] {client_name} requested: {filename}")
                    send_file(client_socket, filename)
                
                # Regular message - Echo back with ACK appended
                else:
                    response = f"{message} ACK"
                    client_socket.send(response.encode())
            
            # Timeout allows checking shutdown_event periodically
            except socket.timeout:
                continue

    except Exception as e:
        print(f"[Error] {client_name}: {e}")
    
    finally:
        # Update cache with disconnection time (thread-safe)
        if client_name:
            with cache_lock:
                if client_name in client_cache:
                    client_cache[client_name]['disconnected_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with active_client_lock:
            active_clients -= 1

        # Close socket connection
        client_socket.close()
        print(f"[Closed] {client_name} connection closed")
        print(f"[Info] Active clients: {active_clients}/{MAX_CLIENTS}")


def format_cache():
    """
    Formats the client connection cache for display to clients.
    """
    with cache_lock:  # Thread-safe read
        if not client_cache:
            return "No clients in cache at the moment"
        
        # Build formatted string
        status = "-----Client Connection Cache-----\n"
        for name, info in client_cache.items():
            status += f"\n{name}:\n"
            status += f"  Address: {info['address']}\n"
            status += f"  Connected: {info['connected_at']}\n"
            status += f"  Disconnected: {info.get('disconnected_at') or 'Still connected'}\n"

        return status


def server():
    """
    Initializes and starts the multi-threaded TCP server.
    
    This is the main server function that:
    1. Initializes the file repository
    2. Creates and configures the server socket
    3. Listens for client connections
    4. Spawns threads to handle each client
    5. Enforces the MAX_CLIENTS limit
    6. Handles graceful shutdown on Ctrl+C
    
    Server Configuration:
        - Host: 127.0.0.1 (localhost)
        - Port: 12000
        - Max Clients: 3
        - Protocol: TCP (SOCK_STREAM)
    
    Socket Options:
        - SO_REUSEADDR: Allows immediate restart without TIME_WAIT delay
        - Timeout: 1 second (allows periodic shutdown_event checking)
    
    Thread Management:
        - Each client gets its own daemon thread
        - Daemon threads automatically terminate when main program exits
        - All threads tracked for graceful shutdown
    
    Graceful Shutdown:
        - Triggered by KeyboardInterrupt (Ctrl+C)
        - Sets shutdown_event to signal all threads
        - Waits for all client threads to finish (join)
        - Closes server socket
    """
    global active_clients

    # Ensure file repository exists and is populated
    initialize_file_repo()

    # Create TCP socket
    serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # Allow immediate restart without waiting for TIME_WAIT expiration
    serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # Set timeout to allow periodic checking of shutdown_event
    serverSocket.settimeout(1.0)

    try:
        serverSocket.bind((HOST, serverPort))
        
        # Start listening for connections 
        serverSocket.listen()

        print("-" * 50)
        print(f"[Server] Started on {HOST}:{serverPort}")
        print(f"[Server] Maximum concurrent clients: {MAX_CLIENTS}")
        print(f"[Server] File repository: {FILE_REPO}/")
        print("-" * 50)
        print("[Server] Waiting for connections...")

        # Track all client threads for graceful shutdown
        client_threads = []

        # MAIN SERVER LOOP 
        # Accept connections until shutdown is requested
        while not shutdown_event.is_set():
            try:
                # Accept incoming connection (blocks until connection or timeout)
                client_socket, client_address = serverSocket.accept()

                # Check if server is at capacity 
                with active_client_lock:
                    if active_clients >= MAX_CLIENTS:
                        print(f"[Rejected] Connection from {client_address} - Server at capacity")
                        reject_message = "Maximum clients reached. Server is full. Please try again later."
                        client_socket.send(reject_message.encode())
                        client_socket.close()
                        continue  

                    # Accept connection - increment counter
                    active_clients += 1

                # Create new thread to handle this client
                client_thread = threading.Thread(
                    target=handle_socket_client,   
                    args=(client_socket, client_address)  
                )
                
                # Daemon threads automatically terminate when main program exits
                client_thread.daemon = True
                
                client_thread.start()
                
                # Track thread for graceful shutdown
                client_threads.append(client_thread)
            
            # Timeout allows checking shutdown_event periodically
            except socket.timeout:
                continue

    except KeyboardInterrupt:
        print("\n[Server] Shutting down...")
        
        # Signal all threads to stop
        shutdown_event.set()
        
        # Wait for all client threads to finish
        for t in client_threads:
            t.join(timeout=2.0)  # Wait up to 2 seconds per thread

    except Exception as e:
        print(f"[Error] Server error: {e}")

    finally:
        serverSocket.close()
        print("[Server] Server stopped")


if __name__ == "__main__":
    server()
