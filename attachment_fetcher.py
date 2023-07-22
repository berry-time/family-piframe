#!/usr/bin/env python3

import base64
import datetime
import email.utils
import imaplib
import logging
import os
import re
import ssl

from config_reader import ImapData

class AttachmentFetcher:
    def __init__(
            self,
            cache_data_path: str,
            cache_info_file: str,
            imap_data: ImapData,                # imap login data object
            allowed_file_extensions: list,      # list of allowed file extensions
            allowed_senders: list,              # list of allowed e-mail senders. may include * to allow all
            logger: logging.Logger):            # logger handler/object to log to

        self.connection = None
        self.imap_data = imap_data
        self.cache_data_path = cache_data_path
        self.cache_info_file = cache_info_file
        self.allowed_file_extensions = allowed_file_extensions
        self.allowed_senders = allowed_senders
        self.logger = logger

    def run(self) -> bool:
        """ Connect to mailserver and fetch new attachments, if available. """
        new_attachments = self._update_cache()
        return new_attachments

    #############################################
    # private functions of AttachmentFetcher
    #############################################
    def _is_valid_file(self, file_name: str) -> bool:
        return file_name.lower().endswith(self.allowed_file_extensions)

    def _is_valid_sender(self, sender_name: str) -> bool:
        return "*" in self.allowed_senders or sender_name in self.allowed_senders
    
    def _get_files_in_folder(self, folder_path: str) -> list:
        if not os.path.isdir(folder_path):
            return []
        folder_entries = os.listdir(folder_path)
        folder_matches = [f for f in folder_entries if os.path.isfile(os.path.join(folder_path, f))]
        return folder_matches

    def _get_cache(self):
        if not os.path.isdir(self.cache_data_path):
            self.logger.info("Cache folder {} does not exist.. creating it.".format(self.cache_data_path))
            os.makedirs(self.cache_data_path)
        cache_info = self._get_files_in_folder(self.cache_data_path)
        self.logger.info("Found {} files in cache {}".format(len(cache_info), self.cache_data_path))
        return cache_info

    def _open_connection(self):
        try:
            ssl_context=ssl.create_default_context()
            ssl_context.verify_mode=ssl.CERT_REQUIRED

            self.connection = imaplib.IMAP4_SSL(
                host=self.imap_data.host,
                port=self.imap_data.port,
                ssl_context=ssl_context)
            
            self.connection.login(
                self.imap_data.user,
                self.imap_data.passwd)
            
        except Exception:
            self.logger.error("Could not login to {}:{} with user {}".format(
                self.imap_data.host, self.imap_data.port, self.imap_data.user))
            self.connection = None

        if self.connection is not None:
            self.logger.info("Connected to {}:{} as {}".format(
                self.imap_data.host, self.imap_data.port, self.imap_data.user))

    def _select_inbox(self):
        try:
            response_code, _ = self.connection.select('INBOX')
            if response_code != "OK":
                self.logger.error("Selecting INBOX failed. Response code: " + response_code + "\nResetting connection.")
                self.connection = None
        except Exception as e:
            self.logger.error("Selecting INBOX failed (error: " + str(e) + "). Resetting connection.")
            self.connection = None

    @staticmethod
    def _unique_attachment_name(email_datetime: datetime.datetime, email_sender: str, attachment_name: str):
        email_sender_encoded = base64.urlsafe_b64encode(email_sender.encode('ascii')).decode('ascii')
        filename_encoded = base64.urlsafe_b64encode(attachment_name.encode('ascii')).decode('ascii')
        return "__".join([email_datetime.strftime("%Y-%m-%d_%H-%M-%S"), email_sender_encoded, filename_encoded])

    def _mail_info(self, uid):
        mail_info = []
        # email internal date-time
        _, internal_date = self.connection.fetch(uid, '(INTERNALDATE)')
        email_datetime = datetime.datetime(*imaplib.Internaldate2tuple(internal_date[0])[:6])
        # get sender
        _, field_from = self.connection.fetch(uid, '(BODY[HEADER.FIELDS (FROM)])')
        email_from = email.utils.parseaddr(field_from[0][1].decode("utf-8"))[1]
        # attachment names
        _, body_structure = self.connection.fetch(uid, '(BODYSTRUCTURE)')
        attachment_names = re.findall("\"filename\" \"(.+?)\"", body_structure[0].decode("utf-8"))

        for attachment_name in attachment_names:
            email_data = {
                "email_uid": uid,
                "email_datetime": email_datetime,
                "email_from": email_from,
                "attachment_name": attachment_name,
                "mangled_name": self._unique_attachment_name(email_datetime, email_from, attachment_name)}

            if self._is_valid_file(attachment_name) and self._is_valid_sender(email_from):
                mail_info.append(email_data)
        
        return mail_info

    def _search_all(self):
        """ Searches all e-mails for matching criteria (file type, sender), returns list of all matches."""
        mail_infos = []
        try:
            response_code, matches = self.connection.search(None, 'ALL')
            if response_code != "OK":
                self.logger.error("Search for E-Mails failed.")
                return mail_infos

            # found matches. Extract mail info and return it
            for uid in matches[0].split():
                mail_infos += self._mail_info(uid)

            return mail_infos

        except Exception as e:
            self.logger.error("Searching INBOX failed. Resetting connection.")
            self.connection = None
        return mail_infos

    @staticmethod
    def _find_emails_to_download(cache_info: dict, mail_infos: list):
        email_uids_to_download = set()
        cache_without_extensions = [os.path.splitext(entry)[0] for entry in cache_info]
        for entry in mail_infos:
            if entry["mangled_name"] not in cache_without_extensions:
                email_uids_to_download.add(entry["email_uid"])
        return email_uids_to_download

    def _download_email_attachments(self, email_uids, cache_path: str):
        self.logger.info("Downloading {} new e-mail(s) from server.".format(len(email_uids)))
        for email_uid in email_uids:
            email_info = self._mail_info(email_uid)[0]
            _, data = self.connection.fetch(email_uid, "(BODY.PEEK[])")
            email_body = data[0][1]
            mail = email.message_from_string(email_body.decode("utf-8"))
            if mail.get_content_maintype() != 'multipart':
                self.logger.error("Requested to download e-mail {}, but is not of type 'multipart'".format(email_uid))
                continue

            for part in mail.walk():
                if part.get_content_maintype() == 'multipart' or part.get('Content-Disposition') is None:
                    continue
                # validity of a file-name needs to be re-checked because an e-mail may contain valid and invalid attachments
                # validity of the sender does NOT need to be re-checked (only valid sender e-mails in uid list)
                if part.get_filename() is None or not self._is_valid_file(part.get_filename()):
                    continue
                # found a valid attachment, let's download it
                self.logger.info("Downloading file {}".format(part.get_filename()))
                output_name = self._unique_attachment_name(
                    email_info["email_datetime"], email_info["email_from"], part.get_filename())
                extension = os.path.splitext(part.get_filename())[1].lower()
                open(os.path.join(cache_path, output_name + extension), 'wb').write(part.get_payload(decode=True))

    def _update_cache_txt_file(self):
        cached_list = self._get_cache()
        with open(self.cache_info_file, "w") as cache_txt_fh:
            for file in cached_list:
                cache_txt_fh.write(os.path.join(self.cache_data_path, file) + "\n")
        
    def _update_cache(self) -> bool:
        cached_list = self._get_cache()
        self._open_connection()
        self._select_inbox()
        mail_infos = self._search_all()
        new_attachments_found = False

        try:
            email_uids_to_download = self._find_emails_to_download(cached_list, mail_infos)
            self._download_email_attachments(email_uids_to_download, self.cache_data_path)
            new_attachments_found = len(email_uids_to_download) > 0
        except Exception as e:
            self.logger.error("Failed to download new E-Mail attachments. Error was: {}".format(str(e)))
        self._update_cache_txt_file()

        return new_attachments_found
