(function () {
    "use strict";

    angular.module('cm.mailings')
        .component('mailingContent', {
            template: '<iframe id="mailing-content" class="mailing-content" src="about:blank">Error loading content</iframe>',
            controller: MailingContentController,
            bindings: {
                mailingId: '<',
                height: '<'
            }
        });

    function MailingContentController($scope, $log, $timeout, gettextCatalog, api, $http, $q) {
        var vm = this;
        $log.debug("MailingID:", vm.mailingId);

        vm.$onChanges = function (changesObj) {
            if (changesObj.mailingId) {
                $log.debug("Mailing ID has changed. Reloading content...");
                loadContent();
            }
            if (changesObj.height) {
                $log.debug("height has changed.");


            }
        };

        function setHeightFromContent(delay) {
            $timeout(function () {
                var iframe = $('#mailing-content').get(0);
                var iFrameHeight = iframe.contentWindow.document.body.scrollHeight + 'px';
                if(iFrameHeight === '0px'){
                    // $log.debug("iframe not yet ready");
                    setHeightFromContent(delay);
                    return;
                }
                // $log.debug("Height:", iFrameHeight);
                iframe.style.height = iFrameHeight;
            }, delay);
        }

        function setContent(data) {
            var iframe = $('#mailing-content').get(0);
            var iframeDoc = iframe.document;
            if (iframe.contentDocument)
                iframeDoc = iframe.contentDocument;
            else if (iframe.contentWindow)
                iframeDoc = iframe.contentWindow.document;

            if (iframeDoc) {
                iframeDoc.open();
                iframeDoc.write(data);
                iframeDoc.close();
                setHeightFromContent(500);
            } else {
                $log.error("Cannot inject dynamic contents into iframe.");
            }
        }

        function loadContent() {
            var contentUrl = '/api/mailings/' + vm.mailingId + '/content';
            $http({method: 'GET', url: contentUrl}).then(
                function (response) {
                    $log.debug(response);
                    var data = response.data.replace('src="cid:', 'src="' + contentUrl + '/cid/');
                    setContent(data);
                },
                function () {
                    setContent("Error loading content");
                });
        }

        if (vm.mailingId)
            loadContent();

    }


}());
