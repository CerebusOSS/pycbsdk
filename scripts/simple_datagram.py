import asyncio
import socket
import logging
from typing import Optional, Tuple


class UDPServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 51002):
        self.host = host
        self.port = port
        self.transport: Optional[asyncio.DatagramTransport] = None

        # Set up logging
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger(__name__)

    class UDPServerProtocol(asyncio.DatagramProtocol):
        def __init__(self, logger):
            self.logger = logger
            self.transport = None

        def connection_made(self, transport: asyncio.DatagramTransport) -> None:
            self.transport = transport
            self.logger.info(f"UDP Server started")

        def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
            message = data.decode()
            self.logger.info(f"Received {message!r} from {addr}")

            try:
                # Parse the datagram - this is where you'd implement your specific parsing logic
                self.parse_datagram(message)

                # Optional: Send a response back to the client
                response = f"Received your message: {message}"
                self.transport.sendto(response.encode(), addr)

            except Exception as e:
                self.logger.error(f"Error processing datagram: {e}")

        def parse_datagram(self, message: str) -> None:
            """
            Implement your custom datagram parsing logic here.
            This is just a simple example that splits the message on commas.
            """
            try:
                # Example: Parse comma-separated values
                parts = message.strip().split(",")
                self.logger.info(f"Parsed {len(parts)} fields from datagram: {parts}")

                # Add your specific parsing logic here
                # For example, if you're expecting a specific format:
                if len(parts) >= 3:
                    timestamp = parts[0]
                    message_type = parts[1]
                    payload = parts[2:]
                    self.logger.info(
                        f"Timestamp: {timestamp}, "
                        f"Type: {message_type}, "
                        f"Payload: {payload}"
                    )

            except Exception as e:
                raise ValueError(f"Failed to parse datagram: {e}")

        def error_received(self, exc: Exception) -> None:
            self.logger.error(f"Error received: {exc}")

    async def start_server(self) -> None:
        """Start the UDP server."""
        try:
            loop = asyncio.get_running_loop()

            # Create a UDP socket with broadcast support
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind((self.host, self.port))

            # Create the UDP endpoint using the configured socket
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: self.UDPServerProtocol(self.logger), sock=sock
            )

            self.transport = transport
            self.logger.info(f"Server listening on {self.host}:{self.port}")

            # Keep the server running
            try:
                while True:
                    await asyncio.sleep(3600)  # Keep alive
            except asyncio.CancelledError:
                self.logger.info("Server shutdown requested")
            finally:
                transport.close()
                sock.close()

        except Exception as e:
            self.logger.error(f"Failed to start server: {e}")
            raise


async def main():
    # Create and start the UDP server
    server = UDPServer()  # Using 0.0.0.0 by default now
    try:
        await server.start_server()
    except KeyboardInterrupt:
        print("\nShutting down server...")


if __name__ == "__main__":
    asyncio.run(main())
