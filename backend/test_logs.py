
import docker, time
client = docker.from_env()
c = client.containers.run('alpine', 'sh -c "while true; do echo hello; sleep 1; done"', detach=True)
time.sleep(2)
for chunk in c.logs(stream=True, tail=25, stdout=True, stderr=True):
    print(chunk)
    break
for chunk in c.logs(stream=True, tail=25, stdout=True, stderr=True, follow=True):
    print(chunk)
    break
c.remove(force=True)

