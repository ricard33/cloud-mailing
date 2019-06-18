(function () {
    "use strict";

    angular.module('cm.mailings')
        .controller('MailingDetailsController', MailingDetailsController)
    ;

    function MailingDetailsController(mailing, $log, $http, mailingService, api, gettextCatalog, stHelper,
                                      $stateParams, $location, alert, $state, $timeout, $scope) {
        var vm = this;
        vm.isLoading = true;
        vm.mailingId = mailing.id;
        vm.mailing = mailing;
        vm.recipients = undefined; //api.recipients.query({"mailing": vm.mailingId, ".filter": "default_with_total"});
        vm.get_css_class = get_css_class;
        vm.recipient_status = ['READY', 'IN_PROGRESS', 'WARNING', 'FINISHED', 'ERROR', 'TIMEOUT', 'GENERAL_ERROR'];
        vm.itemByPage = 100;
        vm.getRecipients = getRecipients;
        vm.startMailing = function () {
            mailingService.startMailing(vm.mailing)
        };
        vm.pauseMailing = function () {
            mailingService.pauseMailing(vm.mailing)
        };
        vm.deleteMailing = function () {
            mailingService.deleteMailing(vm.mailing).then(function (d) {
                $state.go('mailings')
            })
        };
        vm.stopMailing = function () {
            mailingService.stopMailing(vm.mailing)
        };
        vm.date_pickers_opened = {
            scheduled_start: false,
            scheduled_end: false
        };
        vm.openDatePicker = openDatePicker;
        vm.dateOptions = {};
        vm.saveMailing = saveMailing;
        vm.resetMailing = resetMailing;
        vm.selectTab = selectTab;
        vm.tabs = {};


        if ($stateParams.p !== undefined) {
            vm.tabs[$stateParams.p] = true;
        }
        $log.debug(vm.mailing.scheduled_start);
        if (vm.mailing.scheduled_start !== null)
            vm.mailing.scheduled_start = new Date(vm.mailing.scheduled_start);
        if (vm.mailing.scheduled_end !== null)
            vm.mailing.scheduled_end = new Date(vm.mailing.scheduled_end);

        function get_css_class(status) {
            if (status == 'READY') return '';
            else if (status == 'IN_PROGRESS') return '';
            else if (status == 'WARNING') return 'softbounce';
            else if (status == 'FINISHED') return 'delivered';
            else if (status == 'ERROR') return 'hardbounce';
            else if (status == 'TIMEOUT') return 'softbounce';
            else if (status == 'GENERAL_ERROR') return 'hardbounce';
        }


        function update(obj/*, …*/) {
            for (var i = 1; i < arguments.length; i++) {
                for (var prop in arguments[i]) {
                    var val = arguments[i][prop];
                    if (typeof val == "object") // this also applies to arrays or null!
                        update(obj[prop], val);
                    else
                        obj[prop] = val;
                }
            }
            return obj;
        }

        function getRecipients(tableState) {
            //$log.debug(getRecipients);
            vm.isLoading = true;
            //vm.recipients = undefined;
            var limit = tableState.pagination.number || vm.itemByPage;
            var params = {
                "mailing": vm.mailingId, ".filter": "default_with_total",
                ".offset": tableState.pagination.start || 0,
                ".limit": limit,
                ".sort": stHelper.addOrderingPrefix(tableState)
            };
            update(params, stHelper.getSearch(tableState));

            //$log.debug("getRecipients()", params);
            api.recipients.query(params).$promise.then(function (data) {
                vm.recipients = data;

                tableState.pagination.numberOfPages = Math.floor((vm.recipients.total - 1) / limit) + 1;
                vm.isLoading = false;
            });
        }

        function openDatePicker(name) {
            vm.date_pickers_opened[name] = true;
        }

        function saveMailing(mailingForm) {
            //vm.mailing.$patch({subject: vm.mailing.subject})
            var params = {charset: "utf-8"};
            Object.keys(mailingForm).forEach(function (key) {
                if (mailingForm[key] && mailingForm[key].$dirty) {
                    // $log.debug(key, "-->", vm.mailing[key]);
                    params[key] = vm.mailing[key];
                }
            });
            // var params = {
            //     charset: "utf-8",
            //     type: vm.mailing.type,
            //     satellite_group: vm.mailing.satellite_group,
            //     sender_name: vm.mailing.sender_name,
            //     mail_from: vm.mailing.mail_from,
            //     subject: vm.mailing.subject,
            //     testing: vm.mailing.testing,
            //     backup_customized_emails: vm.mailing.backup_customized_emails,
            //     read_tracking: vm.mailing.read_tracking,
            //     click_tracking: vm.mailing.click_tracking,
            //     tracking_url: vm.mailing.tracking_url,
            //     scheduled_start: vm.mailing.scheduled_start,
            //     scheduled_duration: vm.mailing.scheduled_duration,
            //     scheduled_end: vm.mailing.scheduled_end
            // };
            // Object.keys(params).forEach(function (key) {
            //     if (params[key] == null) {
            //         delete params[key];
            //     }
            // });
            api.mailings.patch({id: vm.mailingId}, params).$promise
                .then(function (ml) {
                        alert.success(gettextCatalog.getString("Mailing successfully saved!"));
                        mailingForm.$setPristine();
                    },
                    function (error) {
                        alert.error(gettextCatalog.getString("Error saving mailing:") + " " + error.statusText, null, error);
                    });
        }

        function selectTab(name) {
            //$log.debug("select tab ", name);
            $location.search('p', name);
        }

        function resetMailing(mailingForm) {
            vm.mailing = api.mailings.get({id: vm.mailingId});
            mailingForm.$setPristine();
        }
    }

}());
