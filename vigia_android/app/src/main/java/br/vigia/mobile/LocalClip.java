package br.vigia.mobile;

import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.media.MediaCodec;
import android.media.MediaFormat;
import android.media.MediaMuxer;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.os.ParcelFileDescriptor;
import android.provider.MediaStore;
import java.io.File;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.UUID;

/** Used only on the video worker. Publishes a playable clip after finalizing its MP4. */
final class LocalClip {
    private final Context context;
    private final MediaCodec.BufferInfo sample = new MediaCodec.BufferInfo();
    private Uri uri;
    private File pending, destination;
    private MediaMuxer muxer;
    private int track;
    private long lastStamp, elapsedTicks, lastTime;
    private boolean started, wroteFrame;

    LocalClip(Context context) { this.context = context; }

    void open(MediaFormat format, long stamp) throws IOException {
        String day = new SimpleDateFormat("yyyy-MM-dd_HH-mm-ss", Locale.ROOT).format(new Date());
        String name = "Vigia_" + day + "_" + UUID.randomUUID().toString().substring(0,8) + ".mp4";
        if (Build.VERSION.SDK_INT >= 29) {
            ContentValues values = new ContentValues();
            values.put("_display_name", name);
            values.put("mime_type", "video/mp4");
            values.put("relative_path", Environment.DIRECTORY_MOVIES + "/Vigia");
            values.put("is_pending", 1);
            ContentResolver resolver = context.getContentResolver();
            uri = resolver.insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, values);
            if (uri == null) throw new IOException("Não foi possível criar o clipe.");
            try (ParcelFileDescriptor file = resolver.openFileDescriptor(uri, "rw")) {
                if (file == null) throw new IOException("Não foi possível abrir o clipe.");
                muxer = new MediaMuxer(file.getFileDescriptor(), MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
            }
        } else {
            File dir = context.getExternalFilesDir(Environment.DIRECTORY_MOVIES);
            if (dir == null) throw new IOException("Pasta de vídeos indisponível.");
            destination = new File(dir, name);
            pending = File.createTempFile("gravando-", ".tmp", dir);
            muxer = new MediaMuxer(pending.getAbsolutePath(), MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
        }
        track = muxer.addTrack(format);
        muxer.start();
        started = true;
        lastStamp = stamp;
        elapsedTicks = 0;
        lastTime = -1;
    }

    void write(byte[] data, long stamp, boolean key) {
        // Signed modular delta handles RTP wrap and small timestamp reordering.
        elapsedTicks += (int) (stamp - lastStamp);
        lastStamp = stamp;
        long time = elapsedTicks * 1000 / 90;
        time = Math.max(lastTime + 1, time);
        sample.set(0, data.length, time, key ? MediaCodec.BUFFER_FLAG_KEY_FRAME : 0);
        muxer.writeSampleData(track, ByteBuffer.wrap(data), sample);
        lastTime = time;
        wroteFrame = true;
    }

    boolean finish(boolean keep) {
        boolean success = keep && started && wroteFrame;
        try {
            if (started) muxer.stop();
        } catch (RuntimeException e) { success = false; }
        finally {
            if (muxer != null) {
                try { muxer.release(); } catch (RuntimeException e) { success = false; }
            }
        }
        try {
            if (success && uri != null) {
                ContentValues values = new ContentValues();
                values.put("is_pending", 0);
                success = context.getContentResolver().update(uri, values, null, null) == 1;
            }
            if (success && pending != null) success = pending.renameTo(destination);
        } catch (RuntimeException e) { success = false; }
        if (!success) {
            if (uri != null) {
                try { context.getContentResolver().delete(uri, null, null); }
                catch (RuntimeException ignored) {}
            }
            if (pending != null) pending.delete();
        }
        return success;
    }
}
