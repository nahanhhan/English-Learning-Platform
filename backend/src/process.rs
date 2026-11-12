use std::{
    io::{self, Read, Write},
    process::{Command, Output, Stdio},
    thread,
    time::{Duration, Instant},
};

pub fn hidden(command: &mut Command) -> &mut Command {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x0800_0000);
    }
    command
}

pub fn output(command: &mut Command, input: Vec<u8>, timeout: Duration) -> io::Result<Output> {
    let mut child = hidden(command)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    let mut stdin = child.stdin.take().unwrap();
    let stdout = child.stdout.take().unwrap();
    let stderr = child.stderr.take().unwrap();
    let input_writer = thread::spawn(move || stdin.write_all(&input));
    let read = |mut pipe: Box<dyn Read + Send>| {
        thread::spawn(move || {
            let mut data = Vec::new();
            pipe.read_to_end(&mut data)?;
            Ok::<_, io::Error>(data)
        })
    };
    let stdout_reader = read(Box::new(stdout));
    let stderr_reader = read(Box::new(stderr));
    let started = Instant::now();
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        if started.elapsed() >= timeout {
            #[cfg(windows)]
            let _ = hidden(&mut Command::new("taskkill.exe"))
                .args(["/PID", &child.id().to_string(), "/T", "/F"])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
            let _ = child.kill();
            let _ = child.wait();
            return Err(io::Error::new(io::ErrorKind::TimedOut, "process timed out"));
        }
        thread::sleep(Duration::from_millis(15));
    };
    let _ = input_writer.join();
    let wait = |reader: thread::JoinHandle<io::Result<Vec<u8>>>| {
        reader
            .join()
            .map_err(|_| io::Error::other("process reader failed"))?
    };
    Ok(Output {
        status,
        stdout: wait(stdout_reader)?,
        stderr: wait(stderr_reader)?,
    })
}
