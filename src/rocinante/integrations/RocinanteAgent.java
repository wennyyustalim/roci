import java.awt.Component;
import java.awt.Container;
import java.awt.Frame;
import java.io.File;
import java.lang.instrument.Instrumentation;
import java.lang.reflect.Method;
import java.nio.file.*;
import java.util.*;
import javax.swing.SwingUtilities;

/** Local file bridge: mutate only the managed rocket, on Swing's event thread. */
public class RocinanteAgent {
    private static volatile Path command;
    private static Thread watcher;
    private static Class<?> frameClass;
    private static Frame managedFrame;
    private static String loadedDigest = "";

    public static synchronized void agentmain(String path, Instrumentation inst) throws Exception {
        command = Paths.get(path);
        for (Frame frame : Frame.getFrames()) {
            if (frame.getClass().getName().equals("info.openrocket.swing.gui.main.BasicFrame") && frame.isDisplayable()) frameClass = frame.getClass();
        }
        if (frameClass == null) throw new IllegalStateException("OpenRocket has no ready document window");
        if (watcher != null) return;
        watcher = new Thread(() -> {
            String previous = "";
            while (true) {
                try {
                    Path current = command;
                    Properties props = new Properties();
                    try (var in = Files.newInputStream(current)) { props.load(in); }
                    String request = props.getProperty("request_id");
                    if (request != null && !request.equals(previous)) {
                        try {
                            SwingUtilities.invokeAndWait(() -> {
                                try { update(props, current); }
                                catch (Exception error) { throw new RuntimeException(error); }
                            });
                        } catch (Exception error) {
                            Throwable cause = error;
                            while (cause.getCause() != null) cause = cause.getCause();
                            java.io.StringWriter trace = new java.io.StringWriter(); error.printStackTrace(new java.io.PrintWriter(trace));
                            Files.writeString(current.resolveSibling("openrocket-bridge-error.log"), trace.toString());
                            status(current, request, "error", cause.toString());
                        }
                        previous = request;
                    }
                    Thread.sleep(200);
                } catch (InterruptedException done) { return; }
                catch (Exception error) { try { Thread.sleep(500); } catch (InterruptedException done) { return; } }
            }
        }, "Rocinante document bridge");
        watcher.setDaemon(true);
        watcher.start();
    }

    private static Object call(Object target, String name, Object... args) throws Exception {
        for (Method method : target.getClass().getMethods()) {
            if (!method.getName().equals(name) || method.getParameterCount() != args.length) continue;
            Class<?>[] types = method.getParameterTypes();
            boolean matches = true;
            for (int i = 0; i < args.length; i++) {
                if (types[i].isPrimitive()) {
                    if (!(args[i] instanceof Boolean && types[i] == boolean.class) &&
                        !(args[i] instanceof Integer && types[i] == int.class)) matches = false;
                } else if (args[i] != null && !types[i].isInstance(args[i])) matches = false;
            }
            if (matches) return method.invoke(target, args);
        }
        throw new NoSuchMethodException(target.getClass().getName() + "." + name);
    }

    private static void fit(Component component) throws Exception {
        if (component.getClass().getName().endsWith("ScaleScrollPane")) call(component, "setFitting", true);
        if (component instanceof Container) for (Component child : ((Container) component).getComponents()) fit(child);
    }

    private static void update(Properties props, Path commandPath) throws Exception {
        File file = new File(new String(Base64.getDecoder().decode(props.getProperty("file")), java.nio.charset.StandardCharsets.UTF_8));
        Path allowed = commandPath.getParent().resolve("torpedo").toRealPath();
        if (!file.toPath().toRealPath().startsWith(allowed)) throw new IllegalArgumentException("File is outside this workshop's torpedo directory");
        List<Frame> frames = new ArrayList<>();
        for (Frame candidate : Frame.getFrames()) if (candidate.isDisplayable() && candidate.getClass().getName().equals("info.openrocket.swing.gui.main.BasicFrame")) frames.add(candidate);
        if (managedFrame == null || !managedFrame.isDisplayable()) {
            managedFrame = null;
            for (Object frame : frames) {
                Object doc = call(call(frame, "getRocketPanel"), "getDocument");
                File existing = (File) call(doc, "getFile");
                if (existing != null && existing.toPath().toAbsolutePath().normalize().startsWith(allowed)) {
                    managedFrame = (Frame) frame; break;
                }
            }
        }
        if (managedFrame == null) {
            // No workshop document is open yet (or it was closed by the user).
            // Open it once inside the existing JVM; subsequent selections reuse this frame.
            managedFrame = (Frame) frameClass.getMethod("open", File.class, java.awt.Window.class).invoke(null, file, null);
            if (managedFrame == null) throw new IllegalStateException("OpenRocket could not open the workshop document");
        }
        frameClass = managedFrame.getClass();
        Object panel = call(managedFrame, "getRocketPanel"), doc = call(panel, "getDocument");
        String digest = props.getProperty("digest");
        if (!digest.equals(loadedDigest)) {
            if (!(Boolean) call(doc, "isSaved")) throw new IllegalStateException("Save your manual OpenRocket edits before switching torpedoes");
            Class<?> loaderClass = Class.forName("info.openrocket.core.file.GeneralRocketLoader", true, frameClass.getClassLoader());
            Object incoming = call(loaderClass.getConstructor(File.class).newInstance(file), "load");
            Object rocket = call(doc, "getRocket");
            call(doc, "startUndo", "Workshop torpedo selection");
            try { call(rocket, "loadFrom", call(incoming, "getRocket")); }
            finally { call(doc, "stopUndo"); }
            // Saved simulation results refer to the previous rocket shape.
            while ((Integer) call(doc, "getSimulationCount") > 0) call(doc, "removeSimulation", 0);
            call(doc, "setFile", file); call(doc, "setSaved", true);
            loadedDigest = digest;
        }
        call(managedFrame, "selectTab", 0);
        call(panel, "updateFigures"); fit(managedFrame);
        managedFrame.setTitle(props.getProperty("label", file.getName()) + " — OpenRocket");
        managedFrame.repaint();
        status(commandPath, props.getProperty("request_id"), "synced", "Updated existing OpenRocket window " + System.identityHashCode(managedFrame));
    }

    private static String json(String text) {
        return "\"" + text.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r") + "\"";
    }
    private static void status(Path command, String request, String state, String message) throws Exception {
        Path out = command.resolveSibling("openrocket-selection-status.json"), temp = out.resolveSibling(out.getFileName() + ".tmp");
        Files.writeString(temp, "{\"request_id\":" + request + ",\"status\":" + json(state) + ",\"message\":" + json(message) + "}");
        Files.move(temp, out, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
    }
}
