 #  For headless Raspberry Pi using ethernet cable.
 #  This program connects to a ssh server and reports
 #  its own ip address.
import paramiko, netifaces
netifaces.ifaddresses('eth0')
ip=netifaces.ifaddresses('eth0')[2][0]['addr']
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
 # edit the next line to login
ssh.connect('', username='', password='')
stdin, stdout, stderr = ssh.exec_command("touch "+ip)
ssh.close()
