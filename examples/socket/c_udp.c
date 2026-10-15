#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <winsock2.h>
#else
#include <unistd.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#define closesocket close
#define SOCKET int
#endif
int main(void) {
#ifdef _WIN32
    WSADATA w; if (WSAStartup(MAKEWORD(2,2),&w)) return 1;
#endif
    SOCKET server=socket(AF_INET,SOCK_DGRAM,0), client=socket(AF_INET,SOCK_DGRAM,0);
    struct sockaddr_in addr,peer; memset(&addr,0,sizeof addr); addr.sin_family=AF_INET; addr.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    if(bind(server,(struct sockaddr*)&addr,sizeof addr)) return 2;
#ifdef _WIN32
    int len=sizeof addr,peerlen=sizeof peer;
#else
    socklen_t len=sizeof addr,peerlen=sizeof peer;
#endif
    getsockname(server,(struct sockaddr*)&addr,&len); char data[128]={0};
    const char *message="C UDP datagram"; sendto(client,message,(int)strlen(message),0,(struct sockaddr*)&addr,sizeof addr);
    int n=recvfrom(server,data,sizeof(data)-1,0,(struct sockaddr*)&peer,&peerlen); if(n<=0) return 3;
    sendto(server,data,n,0,(struct sockaddr*)&peer,peerlen); memset(data,0,sizeof data);
    n=recvfrom(client,data,sizeof(data)-1,0,NULL,NULL); if(n<=0) return 4;
    printf("%s\n",data); closesocket(client); closesocket(server);
#ifdef _WIN32
    WSACleanup();
#endif
    return 0;
}
