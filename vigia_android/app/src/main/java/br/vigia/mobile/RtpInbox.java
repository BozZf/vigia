package br.vigia.mobile;

import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketTimeoutException;
import java.util.Arrays;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;

/** Keeps draining the UDP socket while a decoder, speaker or MP4 writer is busy. */
final class RtpInbox implements AutoCloseable {
    private final ArrayBlockingQueue<byte[]> packets=new ArrayBlockingQueue<>(512);
    private final Thread reader;
    private final DatagramSocket socket;
    private volatile boolean closed;
    private volatile IOException failure;

    RtpInbox(DatagramSocket socket, InetAddress camera, int payload){
        this.socket=socket;
        reader=new Thread(()->read(camera,payload),"vigia-receber-rtp");
        reader.start();
    }

    private void read(InetAddress camera,int payload){
        byte[] buffer=new byte[65535];
        DatagramPacket packet=new DatagramPacket(buffer,buffer.length);
        try {
            while(!closed){
                packet.setLength(buffer.length);
                try {socket.receive(packet);} catch(SocketTimeoutException idle){continue;}
                int length=packet.getLength();
                if(length>=12 && camera.equals(packet.getAddress()) && (buffer[1]&127)==payload
                        && packets.remainingCapacity()>0)
                    packets.offer(Arrays.copyOf(buffer,length));
            }
        } catch(IOException e){if(!closed)failure=e;}
    }

    byte[] poll() throws IOException,InterruptedException {
        byte[] packet=packets.poll(200,TimeUnit.MILLISECONDS);
        if(packet==null && failure!=null)throw failure;
        return packet;
    }

    public void close(){
        closed=true;
        socket.close();
        try {reader.join();} catch(InterruptedException e){Thread.currentThread().interrupt();}
    }
}
