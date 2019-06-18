"use strict";

angular.module('app')

.controller('MessageBoxCtrl', ['$scope', '$uibModalInstance', 'modalContent',
    function ($scope, $uibModalInstance, modalContent) {

        $scope.message = modalContent.message;
        $scope.modal_title = modalContent.title;

        $scope.ok = function () {
            $uibModalInstance.close();
        };

        $scope.cancel = function () {
            $uibModalInstance.dismiss();
        };
    }])

.factory('MessageBox', ['$uibModal', 'gettextCatalog', function ($uibModal, gettextCatalog) {
        return {
            open: function(title, message) {
                var modalInstance = $uibModal.open({
                  templateUrl: 'template/ui/message-box.html',
                  controller: 'MessageBoxCtrl',
                  //size: size,
                  resolve: {
                    modalContent: function () {
                      return {
                          title: title,
                          message: message
                      }
                    }
                  }
                });
                return modalInstance;
            }
        }
    }])

;
