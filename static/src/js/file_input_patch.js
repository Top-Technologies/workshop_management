/** @odoo-module **/

import { FileInput } from "@web/core/file_input/file_input";
import { patch } from "@web/core/utils/patch";

/**
 * Odoo FileInput clears the input after upload. If the parent field
 * (e.g. many2many_binary) re-renders during the async upload, the input
 * node is gone and setting .value throws.
 */
patch(FileInput.prototype, {
    async onFileInputChange() {
        this.state.isDisable = true;
        const httpParams = this.httpParams;
        if (this.props.onWillUploadFiles) {
            try {
                const files = await this.props.onWillUploadFiles(httpParams.ufile);
                httpParams.ufile = files;
            } catch (e) {
                this.state.isDisable = false;
                throw e;
            }
        }
        const parsedFileData = await this.uploadFiles(this.props.route, httpParams);
        if (parsedFileData) {
            const inputEl = this.fileInputRef.el;
            this.props.onUpload(
                parsedFileData,
                inputEl ? inputEl.files : []
            );
            if (this.fileInputRef.el) {
                this.fileInputRef.el.value = null;
            }
        }
        this.state.isDisable = false;
    },
});
