
__author__ = "Rocketbot"

from email import message
import imaplib
import mimetypes
import os
import re
import smtplib
from email.message import EmailMessage
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import make_msgid
from email.parser import Parser
from email import encoders
import email
from textwrap import dedent

from bs4 import BeautifulSoup
from mailparser import mailparser
import base64


def parse_uid(data):
    print(data)
    data = data.decode()
    pattern_uid = re.compile(r'\d+ \(UID (?P<uid>\d+)\)')
    match = pattern_uid.match(data)
    return match.group('uid')


def get_regex_group(regex, string):
    matches = re.finditer(regex, string, re.MULTILINE)
    return [[group for group in match.groups()] for match in matches]


class Mail:

    def __init__(self, user, pwd, timeout, smtp_host, smtp_port, imap_host, imap_port, pop_host=None, pop_port=None):
        self.user = user
        self.pwd = pwd
        self.timeout = timeout
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.pop_host = pop_host
        self.pop_port = pop_port
        self.pop = None

    def connect_smtp(self):
        print("Connecting smtp")
        self.server = smtplib.SMTP(
            self.smtp_host, self.smtp_port, timeout=self.timeout)
        self.server.starttls()
        print(self.server.login(self.user, self.pwd))
        return self.server

    def connect_imap(self):
        print("Connecting Imap")
        try:
            self.imap = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
        except:
            self.imap = imaplib.IMAP4(self.imap_host, self.imap_port)

        print(self.imap.login(self.user, self.pwd))
        return self.imap


    def add_body(self, msg, body):
        if not body:
            body = ""
        body = body.replace("\n", "<br>")
                
        if not "src" in body:
            msg.attach(MIMEText(body, 'html'))
            return msg

        for match in get_regex_group(r"src=\"(.*)\"", body):
            path = match[0]
            
            if path.startswith(("http", "https")):
                msg.attach(MIMEText(body, 'html'))
                continue

            image_cid = make_msgid()
            body = body.replace(path, "cid:" + image_cid[1:-1])

            msg.attach(MIMEText(body, 'html'))
            
            img_ = open(path, 'rb')
            image = MIMEImage(img_.read())
            img_.close()
            image.add_header('Content-ID', image_cid)
            image.add_header('Content-Disposition', 'inline', filename=os.path.basename(path))
            image.add_header("Content-Transfer-Encoding", "base64")
            msg.attach(image)

            # Codigo original, se cambia porque no reconoce MIMEImage si el path es de un archivo local
            # with open(path, 'rb') as img:

            #     # know the Content-Type of the image
            #     # maintype, subtype = mimetypes.guess_type(img.name)[
            #     #     0].split('/')

            #     maintype, subtype = MIMEImage(img.read()).get_content_type().split('/')
                
            #     msg.get_payload()[0].add_related(img.read(),
                                                    # maintype=maintype,
                                                    # subtype=subtype,
                                                    # cid=image_cid)
            
        return msg

    def add_attachments(self, msg, paths=[]):
        file_paths = []
        for path in paths:
            if os.path.isdir(path):
                file_paths += [os.path.join(path, file)
                               for file in os.listdir(path)]
            if os.path.isfile(path):
                file_paths.append(path)

        for path in file_paths:
            filename = os.path.basename(path)
            with open(path, "rb") as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
                attachment.close()

            encoders.encode_base64(part)
            part.add_header('Content-Disposition',
                            "attachment",filename=filename)
            msg.attach(part)

        return msg

    def create_mail(self, from_, to, subject, cc="", bcc="", type_="message", reference=None):
        type_email = {
            "multipart": MIMEMultipart('related'),
            "message": EmailMessage()
        }
        mail = type_email[type_]
        mail['Message-ID'] = make_msgid()
        
        if reference is not None:
            mail['References'] = mail['In-Reply-To'] = reference.strip()
        
        mail['Subject'] = subject
        mail['to'] = to
        mail['from'] = from_
        mail['Cc'] = cc
        mail['Bcc'] = bcc
        return mail

    def send_mail(self, to, subject, attachments_path=[], body="", cc="", bcc="", type_="message", reference=None):

        msg = self.create_mail(self.user, to, subject,
                               cc=cc, type_=type_, reference=reference)

        msg = self.add_body(msg, body)
        msg = self.add_attachments(msg, attachments_path)
       
        text = msg.as_string()
        
        server = self.connect_smtp()

        sendTo  = to.split(",") + cc.split(",") + bcc.split(",")

        server.sendmail(self.user, sendTo, text.encode('utf-8'))
        
        server.close()

    def get_mail_pop(self, filter_, value):
        count, size = self.pop.stat()
        mails_id = []
        for i in range(count):
            if not filter_:
                mails_id.append(i)
                continue
            res, line, octet = self.pop.retr(i)
            msg_conn = b'\r\n'.join(line).decode('utf-8')
            msg = Parser().parserstr(msg_conn)
            if msg.get(filter_) == value:
                mails_id.append(i)

        return mails_id

    def get_mail(self, filter_, folder):
        if self.pop is not None:
            return get_mail_pop(filter_, folder)
        mail = self.connect_imap()
        mail.list()
        mail.select(folder)

        result, data = mail.search(None, filter_)
        ids = data[0]  # data is a list.
        id_list = ids.split()  # ids is a space separated string
        mail.logout()
        return [b.decode() for b in id_list]

    def save_file(self, folder, filename, content):
        if not os.path.isdir(folder):
            return
        cont = base64.b64decode(content)
        with open(os.path.join(folder, filename), 'wb') as file_:
            file_.write(cont)
            file_.close()

    def parse_body(self, mail):
        try:
            bs = BeautifulSoup(mail.body, 'html.parser').body.get_text()
        except:
            bs = mail.body

        return bs.split('--- mail_boundary ---')[0]

    def get_email_from_id(self, id_, folder, uid = '(RFC822)'):
        mail = self.connect_imap()
        mail.select(folder)
        emails = mail.fetch(id_, uid)
        return emails

    def read_mail(self, id_, folder, att_folder):
        type, data = self.get_email_from_id(id_, folder)
        self.imap.logout()
        print(data)
        raw_email = data[0][1]
        try:
            raw_email_string = raw_email.decode('utf-8')
        except:
            raw_email_string = raw_email.decode('latin-1')
        mail_ = mailparser.parse_from_string(raw_email_string)
        bs = self.parse_body(mail_)
        
        filenames = []
        for att in mail_.attachments:
            name = att['filename']
            name = name.replace("\r","").replace("\n","")
            filenames.append(name)
            self.save_file(att_folder, name, att['payload'])

        return {
            "mail": mail_,
            "date": mail_.date.__str__(),
            'subject': mail_.subject,
            'from': ", ".join([b for (a, b) in mail_.from_]),
            'to': ", ".join([b for (a, b) in mail_.to]),
            'body': mail_.body.split('--- mail_boundary ---'), # It brings the parsed email (index 0) and the html version (index 1)
            'files': filenames 
        }

    def get_attachments(self,  id_, folder, att_folder):
        type, data = self.get_email_from_id(id_, folder)
        self.imap.logout()
        raw_email = data[0][1]
        try:
            raw_email_string = raw_email.decode('utf-8')
        except:
            raw_email_string = raw_email.decode('latin-1')
        mail_ = mailparser.parse_from_string(raw_email_string)
        filenames = []
        for att in mail_.attachments:
            name = att['filename']
            name = name.replace("\r","").replace("\n","")
            filenames.append(name)
            self.save_file(att_folder, name, att['payload'])

    def reply_mail(self, id_, folder, body, att_file, cc_="", bcc_=""):
        type, data = self.get_email_from_id(id_, folder)
        self.imap.logout()

        raw_email = data[0][1]
        origin_mail = email.message_from_bytes(raw_email)
        
        try:
            raw_email_string = raw_email.decode('utf-8')
        except:
            raw_email_string = raw_email.decode('latin-1')
        mail_ = mailparser.parse_from_string(raw_email_string)
        
        self.send_mail(
            to=origin_mail['Reply-To'] or origin_mail['From'],
            cc=cc_,
            bcc=bcc_,
            subject='Re:' + origin_mail['Subject'],
            attachments_path=att_file,
            body=body + '\n\n' + '---------- Original message ----------' + '\n\n' + mail_.body.split('--- mail_boundary ---')[0],
            type_='multipart',
            reference=origin_mail['Message-ID']
        )

    def add_label(self, id_, folder, type_, label):
        type, data = self.get_email_from_id(id_, folder)
        msg_uid = parse_uid(data[0])
        return self.imap.uid(type_, msg_uid, label)

    def move_mail(self, id_, folder, label):
        type, data = self.get_email_from_id(id_, folder, uid="(UID)")
        if isinstance(data[0], tuple):
            data = data[0]
        mail = parse_uid(data[0])
        result = self.imap.uid('COPY', mail, label)
        if result[0] == "OK":
            move, data = self.imap.uid('STORE', mail, '+FLAGS', r'(\Deleted)')
            ret = self.imap.expunge()
            self.imap.logout()
            return ret
        self.imap.logout()
        raise Exception(result[0])

    def forward_email(self, id_, folder, to_, cc_="", bcc_=""):
        
        type, data = self.get_email_from_id(id_, folder)
        self.imap.logout()

        raw_email = data[0][1]

        try:
            raw_email_string = raw_email.decode('utf-8')
        except:
            raw_email_string = raw_email.decode('latin-1')
        mail_ = email.message_from_string(raw_email_string)
        
        subject = 'Fwd: ' + mail_["Subject"]
        
        msg = self.create_mail(self.user, to_, subject,
                                cc=cc_, bcc=bcc_, type_='multipart')
        
        msg.attach(mail_)

        text = msg.as_string()
        
        server = self.connect_smtp()

        sendTo  = to_.split(",") + cc_.split(",") + bcc_.split(",")

        server.sendmail(self.user, sendTo, text.encode('utf-8'))
        
        server.close()

    def mark_as_unread(self, id_, folder):
        type, data = self.get_email_from_id(id_, folder, uid="(UID)")
        msg_uid = parse_uid(data[0])
        
        result = self.imap.uid('STORE', msg_uid, '-FLAGS', r'(\Seen)')
        
        if result[0] != "OK":
            self.imap.logout()
            raise Exception(result[0])

        self.imap.logout()



        

